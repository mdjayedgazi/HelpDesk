"""Reusable ticket business rules shared by the routers."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.permissions import is_admin_role
from app.enums.enums import (
    ImpactLevel,
    Role,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory
from app.models.user import User

# A ticket number starts after 10000 so the first real ticket is 10001.
TICKET_NUMBER_START = 10000

# The supported priority policy for customer-supplied impact. The customer
# states real-world impact; the backend maps it to the ticket priority. The
# client can never set ``priority`` directly (see ``TicketCreate``).
PRIORITY_BY_IMPACT: dict[ImpactLevel, TicketPriority] = {
    ImpactLevel.LOW: TicketPriority.LOW,
    ImpactLevel.MEDIUM: TicketPriority.NORMAL,
    ImpactLevel.HIGH: TicketPriority.HIGH,
    ImpactLevel.CRITICAL: TicketPriority.URGENT,
}


def priority_for_impact(impact: ImpactLevel | None) -> TicketPriority:
    """Map customer-stated impact to the ticket priority.

    No impact given means NORMAL; this mapping is the only way customer input
    reaches the priority field, so the policy cannot be bypassed.
    """
    if impact is None:
        return TicketPriority.NORMAL
    return PRIORITY_BY_IMPACT[impact]


# Which status changes are allowed. CLOSED is terminal: a closed ticket has to
# be reopened through staff intervention, not by a random status jump.
ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    TicketStatus.IN_PROGRESS: {
        TicketStatus.WAITING_ON_CUSTOMER,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    },
    TicketStatus.WAITING_ON_CUSTOMER: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    },
    TicketStatus.RESOLVED: {TicketStatus.IN_PROGRESS, TicketStatus.CLOSED},
    TicketStatus.CLOSED: set(),
}

# Customers may edit their ticket text only while it is still being worked on.
CUSTOMER_EDITABLE_STATUSES = {
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_ON_CUSTOMER,
}


def can_view_ticket(user: User, ticket: Ticket) -> bool:
    """Return True if ``user`` is allowed to see ``ticket``."""
    if is_admin_role(user.role):
        return True
    if user.role == Role.AGENT:
        # Agents see tickets assigned to them and the unassigned queue.
        return ticket.assignee_user_id in (None, user.id)
    return ticket.created_by_user_id == user.id


async def load_visible_ticket(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    user: User,
    *,
    for_update: bool = False,
) -> Ticket:
    """Fetch a ticket the user may see, or raise 404.

    We return 404 (not 403) for tickets the user may not see so that the API
    does not reveal that a private ticket exists.

    ``for_update`` takes a row lock (PostgreSQL) for mutations that must be
    race-free, such as claiming an unassigned ticket. It is a no-op on SQLite.
    """
    ticket = await session.get(Ticket, ticket_id, with_for_update=for_update)
    if ticket is None or not can_view_ticket(user, ticket):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket


async def next_ticket_number(session: AsyncSession) -> int:
    result = await session.exec(select(func.max(Ticket.ticket_number)))
    current = result.one()
    return (current or TICKET_NUMBER_START) + 1


def validate_status_transition(current: TicketStatus, new: TicketStatus) -> None:
    if new == current:
        return
    if new not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change status from {current.value} to {new.value}",
        )


def record_history(
    session: AsyncSession,
    *,
    ticket: Ticket,
    actor: User,
    event_type: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> TicketHistory:
    """Stage a ticket_history row. The caller commits."""
    entry = TicketHistory(
        ticket_id=ticket.id,
        actor_user_id=actor.id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(entry)
    return entry


def ticket_list_filter(user: User):
    """Return the SQL filter that limits which tickets a role may list."""
    if is_admin_role(user.role):
        return None
    if user.role == Role.AGENT:
        return or_(
            Ticket.assignee_user_id == user.id,
            Ticket.assignee_user_id.is_(None),
        )
    return Ticket.created_by_user_id == user.id


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
#
# Every ticket listing is offset-paginated with ``limit``/``offset``. Two rules
# keep page contents stable and make the metadata honest:
#
# 1. Filtering happens *before* the LIMIT/OFFSET window, and the COUNT query is
#    built from exactly the same WHERE clause as the data query, so ``total``
#    can never disagree with the rows on the page.
# 2. Ordering is deterministic: the requested ordering is always followed by a
#    unique tie-breaker (``created_at DESC, id DESC``). A timestamp-only order
#    is not stable when rows share a ``created_at`` (bulk seeding, batch
#    imports): PostgreSQL may return tied rows in a different physical order
#    for each OFFSET, which produces duplicate rows on one page and silently
#    drops others from the next. The id tie-breaker removes that ambiguity.
#
# Offset pagination is still only *snapshot*-consistent: a ticket inserted or
# updated between two page requests can shift rows across the page boundary.
# That is an inherent property of OFFSET; the UI reconciles an out-of-range
# page against the fresh total instead of trusting a stale "has next" guess.


def ticket_list_conditions(
    user: User,
    *,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    assignee_user_id: uuid.UUID | None = None,
    unassigned: bool = False,
    created_by_user_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list:
    """Return the WHERE conditions shared by the COUNT and data queries.

    ``unassigned=True`` restricts to tickets with no assignee. It is applied
    server-side (rather than filtering a page client-side) so pagination and
    ``total`` describe the same result set. ``unassigned`` wins over
    ``assignee_user_id`` when both are present, because "no assignee" is the
    more specific intent and the two cannot both match one row.
    """
    conditions = []

    scope = ticket_list_filter(user)
    if scope is not None:
        conditions.append(scope)

    if status is not None:
        conditions.append(Ticket.status == status)
    if priority is not None:
        conditions.append(Ticket.priority == priority)
    if category is not None:
        conditions.append(Ticket.category == category)
    if unassigned:
        conditions.append(Ticket.assignee_user_id.is_(None))
    elif assignee_user_id is not None:
        conditions.append(Ticket.assignee_user_id == assignee_user_id)
    if created_by_user_id is not None:
        conditions.append(Ticket.created_by_user_id == created_by_user_id)
    if q:
        like = f"%{q.lower()}%"
        conditions.append(or_(Ticket.title.ilike(like)))

    return conditions


async def count_tickets(session: AsyncSession, conditions: list) -> int:
    """Count tickets matching ``conditions`` using the same WHERE as the list."""
    statement = select(func.count()).select_from(Ticket)
    if conditions:
        statement = statement.where(*conditions)
    return int((await session.exec(statement)).one())


def paginate_tickets(conditions: list, *, limit: int, offset: int):
    """Build the deterministic, windowed ticket query.

    Newest first, with the primary key as a unique tie-breaker so rows that
    share a ``created_at`` still have one stable order across every page.
    """
    statement = select(Ticket)
    if conditions:
        statement = statement.where(*conditions)
    return (
        statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(limit)
        .offset(offset)
    )


# The Ticket columns, read from the model so this can never drift from the schema.
_TICKET_COLUMN_NAMES = tuple(column.name for column in Ticket.__table__.columns)


async def count_and_page_tickets(
    session: AsyncSession,
    conditions: list,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    """Return one page of tickets **and** the total count in a single round-trip.

    The list endpoint previously issued two sequential queries (``count(*)`` then
    the page). Against a high-latency database such as Neon — where each
    round-trip can approach hundreds of milliseconds — that doubled the request's
    database latency for no benefit. A window function ``count(*) OVER ()``
    returns the full filtered total alongside each page row, so one round-trip
    yields both values.

    The count is computed over the same filtered set as the page (the window is
    evaluated before ``LIMIT``), so it can never disagree with the data query —
    the exact invariant the previous two-query implementation maintained.

    An empty page still needs the true total (e.g. a deep page past the end), and
    a window function produces no rows to read it from. In that one case we fall
    back to a separate ``COUNT`` — still correct, and only for out-of-range pages,
    which are not the hot path. Ordering is unchanged (``created_at DESC,
    id DESC``) for deterministic pagination.
    """
    # ``session.exec`` unwraps a single-entity SELECT into ``Ticket`` objects,
    # so build an explicit column select: every Ticket column plus the windowed
    # total. This keeps each result row a tuple on every dialect/driver.
    columns = [getattr(Ticket, name) for name in _TICKET_COLUMN_NAMES]
    ordered = select(*columns)
    if conditions:
        ordered = ordered.where(*conditions)
    ordered = ordered.order_by(Ticket.created_at.desc(), Ticket.id.desc())

    total_column = func.count().over().label("__total")
    windowed = ordered.add_columns(total_column).limit(limit).offset(offset)
    result = (await session.exec(windowed)).all()

    if not result:
        # No rows on this page: the true total cannot be read from the window.
        return [], await count_tickets(session, conditions)

    # Each row is ``(*ticket_columns, total)``; the total is identical per row.
    items = [
        Ticket(**dict(zip(_TICKET_COLUMN_NAMES, tuple(row)[:-1], strict=True)))
        for row in result
    ]
    total = int(tuple(result[0])[-1])
    return items, total
