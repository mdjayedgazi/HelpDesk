import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.auth import (
    admin_dependency,
    agent_dependency,
    customer_dependency,
    staff_dependency,
    user_dependency,
)
from app.core.database import session_Dependency
from app.enums.enums import (
    NotificationType,
    Role,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.tickets import (
    TicketAssign,
    TicketContactRead,
    TicketCreate,
    TicketRead,
    TicketStaffUpdate,
)
from app.services.assignment import (
    acquire_assignment_lock,
    pick_assignee,
)
from app.services.notifications import create_notification
from app.services.tickets import (
    CUSTOMER_EDITABLE_STATUSES,
    load_visible_ticket,
    next_ticket_number,
    priority_for_impact,
    record_history,
    ticket_list_filter,
    validate_status_transition,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])

# How many times we try to allocate a fresh ticket number before giving up.
_TICKET_NUMBER_RETRIES = 5


@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    session: session_Dependency,
    customer: customer_dependency,
) -> Ticket:
    """Open a new ticket. Customer-only; the owner is the authenticated user.

    The client chooses the title, description, category, optional impact and
    optional contact phone. Everything else is server-side policy: the status
    starts at ``OPEN``, the priority comes from the impact policy, and the
    ticket is auto-assigned to the least-loaded active agent.

    ``ticket_number`` is generated in Python as ``max + 1``. Two requests can
    pick the same number at the same time, in which case the unique index
    rejects one of them. We retry a bounded number of times, regenerating the
    number on every attempt, and only swallow the specific ticket-number
    unique violation. Any other integrity error is surfaced immediately.

    Auto-assignment runs inside a savepoint: if anything unexpected happens
    there, the savepoint is rolled back and the ticket is still created
    (unassigned) instead of the whole request failing.
    """
    for _ in range(_TICKET_NUMBER_RETRIES):
        ticket = Ticket(
            ticket_number=await next_ticket_number(session),
            title=payload.title,
            description=payload.description,
            category=payload.category,
            contact_phone=payload.contact_phone,
            created_by_user_id=customer.id,
            status=TicketStatus.OPEN,
            # ``impact`` is the only urgency input a customer may give; the
            # supported policy in app.services.tickets maps it to the priority.
            # Restricted fields (status, priority, assignee) are never taken
            # from the request body.
            priority=priority_for_impact(payload.impact),
        )
        try:
            session.add(ticket)
            # Staged in the same transaction as the ticket, so a retry never
            # leaves a duplicate history row behind.
            record_history(
                session,
                ticket=ticket,
                actor=customer,
                event_type="TICKET_CREATED",
                new_value={
                    "status": ticket.status.value,
                    "priority": ticket.priority.value,
                    "category": ticket.category.value,
                    **(
                        {"impact": payload.impact.value}
                        if payload.impact is not None
                        else {}
                    ),
                },
            )
            # flush() assigns the primary key and surfaces a unique violation
            # here, so this block must stay inside the try that handles it.
            await session.flush()
            await _try_auto_assign(session, ticket, customer)
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if not _is_ticket_number_conflict(exc):
                # A different constraint failed; retrying would not help.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not create the ticket",
                ) from exc
            # rollback() expires every object in the session, including the
            # authenticated user. Reload it so the next attempt can read its id.
            await session.refresh(customer)
            continue
        await session.refresh(ticket)
        return ticket

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a ticket number, please retry",
    )


@router.get("", response_model=list[TicketRead])
async def list_tickets(
    session: session_Dependency,
    user: user_dependency,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: Annotated[TicketPriority | None, Query()] = None,
    category: Annotated[TicketCategory | None, Query()] = None,
    assignee_user_id: Annotated[uuid.UUID | None, Query()] = None,
    created_by_user_id: Annotated[uuid.UUID | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=180)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Ticket]:
    """List tickets the user is allowed to see.

    Customers only ever get their own tickets. Agents get their assigned
    tickets plus the unassigned queue. Admins see everything.
    """
    statement = select(Ticket)

    scope = ticket_list_filter(user)
    if scope is not None:
        statement = statement.where(scope)

    if status_filter is not None:
        statement = statement.where(Ticket.status == status_filter)
    if priority is not None:
        statement = statement.where(Ticket.priority == priority)
    if category is not None:
        statement = statement.where(Ticket.category == category)
    if assignee_user_id is not None:
        statement = statement.where(Ticket.assignee_user_id == assignee_user_id)
    if created_by_user_id is not None:
        statement = statement.where(Ticket.created_by_user_id == created_by_user_id)
    if q:
        like = f"%{q.lower()}%"
        statement = statement.where(or_(Ticket.title.ilike(like)))

    statement = statement.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    result = await session.exec(statement)
    return list(result.all())


@router.get("/assigned", response_model=list[TicketRead])
async def list_my_assigned_tickets(
    session: session_Dependency,
    agent: agent_dependency,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Ticket]:
    """The agent's own assigned ticket queue."""
    statement = select(Ticket).where(Ticket.assignee_user_id == agent.id)
    if status_filter is not None:
        statement = statement.where(Ticket.status == status_filter)
    statement = statement.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    result = await session.exec(statement)
    return list(result.all())


@router.get("/{ticket_id}", response_model=TicketRead)
async def get_ticket(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    user: user_dependency,
) -> Ticket:
    return await load_visible_ticket(session, ticket_id, user)


@router.get("/{ticket_id}/contact", response_model=TicketContactRead)
async def get_ticket_contact(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    staff: staff_dependency,
) -> TicketContactRead:
    """The optional contact number of a ticket, for authorized staff only.

    The value is personal information: it is never part of the public/customer
    ticket payload. Staff must still be allowed to view the ticket at all
    (agents only see their own tickets and the unassigned queue).
    """
    ticket = await load_visible_ticket(session, ticket_id, staff)
    return TicketContactRead(
        ticket_id=ticket.id, contact_phone=ticket.contact_phone
    )


@router.patch("/{ticket_id}", response_model=TicketRead)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketStaffUpdate,
    session: session_Dependency,
    user: user_dependency,
) -> Ticket:
    """Role-aware ticket update.

    Customers may edit the title/description/contact phone of their own open
    tickets. Agents may edit those plus the status, priority and category.
    Admins may edit any of those fields.
    """
    ticket = await load_visible_ticket(session, ticket_id, user)
    data = payload.model_dump(exclude_unset=True)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No fields to update",
        )

    # Snapshot the old values so the history entries are accurate.
    old = {
        "status": ticket.status,
        "priority": ticket.priority,
        "title": ticket.title,
        "description": ticket.description,
        "category": ticket.category,
        "contact_phone": ticket.contact_phone,
    }

    if user.role == Role.CUSTOMER:
        forbidden = set(data) - {"title", "description", "contact_phone"}
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Customers may only edit the title, description and "
                    "contact phone"
                ),
            )
        if ticket.status not in CUSTOMER_EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This ticket can no longer be edited",
            )
        _apply_text(ticket, data)
        _apply_contact_phone(ticket, data)

    else:
        # Agents and admins share the same editable fields. Assignment and
        # role changes have their own admin-only endpoints.
        _apply_text(ticket, data)
        _apply_contact_phone(ticket, data)
        if "category" in data:
            ticket.category = data["category"]
        if "priority" in data:
            ticket.priority = data["priority"]
        if "status" in data:
            validate_status_transition(ticket.status, data["status"])
            _set_status(ticket, data["status"])

    _record_changes(
        session,
        ticket=ticket,
        actor=user,
        data=data,
        old=old,
    )

    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/claim", response_model=TicketRead)
async def claim_ticket(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    agent: agent_dependency,
) -> Ticket:
    """An agent claims an unassigned ticket from the queue.

    The row is locked before the check so two simultaneous claims can never
    both succeed: the second request waits, then sees the committed assignee
    and gets a clean ``409``.
    """
    ticket = await load_visible_ticket(session, ticket_id, agent, for_update=True)

    if ticket.assignee_user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This ticket is already assigned",
        )

    ticket.assignee_user_id = agent.id
    ticket.assigned_at = datetime.now(timezone.utc)
    record_history(
        session,
        ticket=ticket,
        actor=agent,
        event_type="TICKET_ASSIGNED",
        old_value={"assignee_user_id": None},
        new_value={
            "assignee_user_id": str(agent.id),
            "reason": "AGENT_CLAIMED",
        },
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/assign", response_model=TicketRead)
async def assign_ticket(
    ticket_id: uuid.UUID,
    payload: TicketAssign,
    session: session_Dependency,
    admin: admin_dependency,
) -> Ticket:
    """Assign or unassign a ticket. Admin only."""
    ticket = await load_visible_ticket(session, ticket_id, admin, for_update=True)
    old_assignee = ticket.assignee_user_id
    await _set_assignee(session, ticket, payload.assignee_user_id, admin)

    if old_assignee != ticket.assignee_user_id:
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

    return ticket


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_ticket_number_conflict(exc: IntegrityError) -> bool:
    """Return True only for a duplicate ``tickets.ticket_number`` violation.

    PostgreSQL (psycopg) exposes the SQLSTATE and constraint name, so we can
    be precise. SQLite and other drivers only give a message, so we fall back
    to matching the column name there.
    """
    orig = getattr(exc, "orig", None)
    message = str(orig or exc).lower()

    # 23505 is the PostgreSQL unique-violation SQLSTATE.
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate is not None and sqlstate != "23505":
        return False

    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag is not None else None
    if constraint:
        return "ticket_number" in constraint

    return "ticket_number" in message


def _apply_text(ticket: Ticket, data: dict) -> None:
    if "title" in data:
        ticket.title = data["title"]
    if "description" in data:
        ticket.description = data["description"]


def _apply_contact_phone(ticket: Ticket, data: dict) -> None:
    """Apply the optional contact phone. Both customers and staff may fix it."""
    if "contact_phone" in data:
        ticket.contact_phone = data["contact_phone"]


def _set_status(ticket: Ticket, new_status: TicketStatus) -> None:
    if new_status == ticket.status:
        return
    if new_status == TicketStatus.RESOLVED:
        ticket.resolved_at = datetime.now(timezone.utc)
    elif ticket.status == TicketStatus.RESOLVED:
        ticket.resolved_at = None
    ticket.status = new_status


async def _set_assignee(
    session,
    ticket: Ticket,
    assignee_user_id: uuid.UUID | None,
    actor: User | None,
) -> None:
    if assignee_user_id is not None:
        assignee = await session.get(User, assignee_user_id)
        if assignee is None or not assignee.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee not found",
            )
        # Tickets are assigned to active agents only. Admins manage the
        # assignment but do not appear in the assignable-agent list.
        if assignee.role != Role.AGENT:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tickets can only be assigned to agents",
            )

    old = ticket.assignee_user_id

    if old == assignee_user_id:
        return

    ticket.assignee_user_id = assignee_user_id
    # ``assigned_at`` drives the fairness tie-break of the automatic
    # assignment service: it is set on every assignment and cleared on
    # unassignment so "last assigned" always reflects reality.
    ticket.assigned_at = (
        datetime.now(timezone.utc) if assignee_user_id is not None else None
    )

    if actor is not None:
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="TICKET_ASSIGNED",
            old_value={"assignee_user_id": str(old) if old else None},
            new_value={"assignee_user_id": str(assignee_user_id) if assignee_user_id else None},
        )

    if assignee_user_id is not None:
        create_notification(
            session,
            recipient_user_id=assignee_user_id,
            related_ticket_id=ticket.id,
            type=NotificationType.TICKET_ASSIGNED,
            title="Ticket assigned to you",
            message=f"Ticket #{ticket.ticket_number} was assigned to you.",
        )


def _record_changes(
    session,
    *,
    ticket: Ticket,
    actor: User,
    data: dict,
    old: dict,
) -> None:
    """Write history rows and notifications for the fields that changed.

    ``old`` holds the pre-update snapshot. The contact phone is personal
    information: history only records *whether* it is present, never the
    number itself.
    """
    if "status" in data and ticket.status != old["status"]:
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="STATUS_CHANGED",
            old_value={"status": old["status"].value},
            new_value={"status": ticket.status.value},
        )
        if ticket.created_by_user_id != actor.id:
            create_notification(
                session,
                recipient_user_id=ticket.created_by_user_id,
                related_ticket_id=ticket.id,
                type=NotificationType.STATUS_CHANGED,
                title="Ticket status updated",
                message=f"Ticket #{ticket.ticket_number} is now {ticket.status.value}.",
            )

    if "priority" in data and ticket.priority != old["priority"]:
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="PRIORITY_CHANGED",
            old_value={"priority": old["priority"].value},
            new_value={"priority": ticket.priority.value},
        )
        if ticket.created_by_user_id != actor.id:
            create_notification(
                session,
                recipient_user_id=ticket.created_by_user_id,
                related_ticket_id=ticket.id,
                type=NotificationType.PRIORITY_CHANGED,
                title="Ticket priority updated",
                message=f"Ticket #{ticket.ticket_number} priority is now {ticket.priority.value}.",
            )

    if "category" in data and ticket.category != old["category"]:
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="CATEGORY_CHANGED",
            old_value={"category": old["category"].value},
            new_value={"category": ticket.category.value},
        )

    if "title" in data and ticket.title != old["title"]:
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="TICKET_UPDATED",
            old_value={"title": old["title"]},
            new_value={"title": ticket.title},
        )

    if "description" in data and ticket.description != old["description"]:
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="TICKET_UPDATED",
            old_value={"description": old["description"]},
            new_value={"description": ticket.description},
        )

    if "contact_phone" in data and ticket.contact_phone != old["contact_phone"]:
        # No PII in history: record only whether a number is on file.
        record_history(
            session,
            ticket=ticket,
            actor=actor,
            event_type="CONTACT_UPDATED",
            old_value={"contact_phone_set": old["contact_phone"] is not None},
            new_value={"contact_phone_set": ticket.contact_phone is not None},
        )


async def _try_auto_assign(session, ticket: Ticket, actor: User) -> bool:
    """Workload-aware automatic assignment for a freshly created ticket.

    Runs after the ticket row is flushed, inside a savepoint: a problem here
    can never lose the ticket or the customer's confirmation. The PostgreSQL
    advisory lock in ``acquire_assignment_lock`` serialises concurrent intake
    decisions so two tickets cannot both be routed to the same agent based on
    a stale workload snapshot.
    """
    try:
        async with session.begin_nested():
            await acquire_assignment_lock(session)
            decision = await pick_assignee(session)

            if decision is None:
                # No eligible agent: keep the ticket safely in the unassigned
                # queue and tell the administrative team.
                await _notify_admins_needs_assignment(session, ticket)
                return False

            ticket.assignee_user_id = decision.agent_id
            ticket.assigned_at = datetime.now(timezone.utc)
            session.add(ticket)

            record_history(
                session,
                ticket=ticket,
                actor=actor,
                event_type="TICKET_ASSIGNED",
                old_value={"assignee_user_id": None},
                new_value={
                    "assignee_user_id": str(decision.agent_id),
                    # The decision inputs are stored with the assignment so
                    # "who was chosen and why" is auditable after the fact.
                    "reason": decision.reason,
                    "weighted_load_at_assignment": decision.weighted_load,
                    "active_tickets_at_assignment": decision.active_tickets,
                    "eligible_agents": decision.eligible_agents,
                },
            )
            create_notification(
                session,
                recipient_user_id=decision.agent_id,
                related_ticket_id=ticket.id,
                type=NotificationType.TICKET_ASSIGNED,
                title="Ticket assigned to you",
                message=f"Ticket #{ticket.ticket_number} was assigned to you.",
            )
        return True
    except Exception:
        # The savepoint has been rolled back: the ticket row is intact and
        # nothing from the failed attempt (assignee, history, notification)
        # survives. The log line carries only the ticket id, never the
        # customer's details.
        logger.exception(
            "Automatic assignment failed for ticket %s; ticket stays unassigned",
            ticket.id,
        )
        # Surface the unassigned ticket to the administrative queue, exactly as
        # when no agent is eligible, so the request is never silently stranded.
        # This is a separate savepoint so a second failure here cannot undo the
        # customer's ticket either.
        try:
            async with session.begin_nested():
                await _notify_admins_needs_assignment(session, ticket)
        except Exception:
            logger.exception(
                "Could not notify administrators about unassigned ticket %s",
                ticket.id,
            )
        return False


async def _notify_admins_needs_assignment(session, ticket: Ticket) -> None:
    """Tell every active ADMIN/OWNER that a ticket needs a manual assignee."""
    recipients = await session.exec(
        select(User).where(
            User.role.in_((Role.ADMIN, Role.OWNER)),
            User.is_active.is_(True),
        )
    )
    for admin in recipients.all():
        create_notification(
            session,
            recipient_user_id=admin.id,
            related_ticket_id=ticket.id,
            type=NotificationType.TICKET_NEEDS_ASSIGNMENT,
            title="Ticket needs an assignee",
            message=(
                f"Ticket #{ticket.ticket_number} could not be auto-assigned. "
                "Please review the queue."
            ),
        )
