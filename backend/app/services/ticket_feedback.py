"""Business rules for customer feedback on a resolved ticket.

Kept intentionally small and single-purpose: one rating + optional comment per
ticket, submitted once by the ticket's own customer after the ticket is
resolved. The backend is the source of truth - the frontend only mirrors these
rules.
"""

import uuid

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.enums.enums import NotificationType, Role, TicketStatus
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.models.ticket_feedback import TicketFeedback
from app.models.user import User

# Feedback is only meaningful once the issue is resolved. CLOSED is deliberately
# excluded: a closed ticket was not necessarily resolved (it can be closed from
# OPEN), so it must not collect satisfaction data.
FEEDBACK_STATUSES: frozenset[TicketStatus] = frozenset({TicketStatus.RESOLVED})

MIN_RATING = 1
MAX_RATING = 5


def is_feedback_eligible(ticket: Ticket) -> bool:
    """Whether the ticket is currently in a feedback-eligible state."""
    return ticket.status in FEEDBACK_STATUSES


def can_submit_feedback(ticket: Ticket, user: User) -> bool:
    """Whether ``user`` may submit feedback for ``ticket`` right now.

    Only the ticket's own customer, and only while the ticket is resolved.
    """
    return (
        user.role == Role.CUSTOMER
        and ticket.created_by_user_id == user.id
        and is_feedback_eligible(ticket)
    )


async def load_feedback(
    session: AsyncSession, ticket_id: uuid.UUID
) -> TicketFeedback | None:
    """The single feedback row for a ticket, or ``None``."""
    return (
        await session.exec(
            select(TicketFeedback).where(TicketFeedback.ticket_id == ticket_id)
        )
    ).first()


async def submit_feedback(
    session: AsyncSession,
    *,
    ticket: Ticket,
    customer: User,
    rating: int,
    comment: str | None,
) -> TicketFeedback:
    """Stage a feedback row for its ticket. Caller commits.

    Raises ``409`` when the ticket already has feedback (single-answer rule), so
    a retried or double-clicked submit can never create a second row.
    """
    if rating < MIN_RATING or rating > MAX_RATING:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Rating must be between {MIN_RATING} and {MAX_RATING}",
        )

    existing = await load_feedback(session, ticket.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback has already been submitted for this ticket",
        )

    feedback = TicketFeedback(
        ticket_id=ticket.id,
        customer_user_id=customer.id,
        rating=rating,
        comment=comment,
    )
    session.add(feedback)

    await _clear_feedback_request(session, ticket_id=ticket.id, customer_id=customer.id)
    return feedback


async def _clear_feedback_request(
    session: AsyncSession, *, ticket_id: uuid.UUID, customer_id: uuid.UUID
) -> None:
    """Mark the customer's outstanding feedback-request notifications read.

    Submitting feedback answers the request, so leaving those notifications
    unread would show a misleading unread badge later.
    """
    rows = (
        await session.exec(
            select(Notification).where(
                Notification.recipient_user_id == customer_id,
                Notification.related_ticket_id == ticket_id,
                Notification.type == NotificationType.TICKET_RESOLVED,
                Notification.is_read.is_(False),
            )
        )
    ).all()
    for row in rows:
        row.is_read = True
        session.add(row)
