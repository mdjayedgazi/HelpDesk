"""Reusable ticket business rules shared by the routers."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.permissions import is_admin_role
from app.enums.enums import ImpactLevel, Role, TicketPriority, TicketStatus
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
