"""Ticket feedback endpoints.

Feedback is a narrow, ticket-scoped resource:

* ``GET`` is available to anyone who may see the ticket (the customer who owns
  it, and staff working it). It returns the single feedback row plus a
  server-computed ``can_submit`` so the client renders the form only when the
  backend would accept the submission.
* ``POST`` is customer-only and only for the ticket's own customer. A resolved
  ticket accepts exactly one answer; a second attempt is a ``409``.

Access to the ticket itself is always re-checked with ``load_visible_ticket``,
which returns ``404`` for a ticket the caller may not see (so the API never
reveals that another customer's ticket exists).
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.auth import customer_dependency, user_dependency
from app.core.database import session_Dependency
from app.enums.enums import Role
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket_feedback import (
    TicketFeedbackCreate,
    TicketFeedbackRead,
    TicketFeedbackState,
)
from app.services.ticket_feedback import (
    can_submit_feedback,
    is_feedback_eligible,
    load_feedback,
    submit_feedback,
)
from app.services.tickets import load_visible_ticket

router = APIRouter(
    prefix="/api/v1/tickets/{ticket_id}/feedback",
    tags=["ticket-feedback"],
)


async def _state(session, ticket: Ticket, viewer: User) -> TicketFeedbackState:
    feedback = await load_feedback(session, ticket.id)
    eligible = is_feedback_eligible(ticket)
    can_submit = can_submit_feedback(ticket, viewer) and feedback is None
    return TicketFeedbackState(
        feedback=(
            TicketFeedbackRead.model_validate(feedback)
            if feedback is not None
            else None
        ),
        can_submit=can_submit,
        awaiting_feedback=(
            eligible
            and feedback is None
            and viewer.role == Role.CUSTOMER
            and ticket.created_by_user_id == viewer.id
        ),
    )


@router.get("", response_model=TicketFeedbackState)
async def get_ticket_feedback(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    user: user_dependency,
) -> TicketFeedbackState:
    """The feedback state for a ticket the caller is allowed to see."""
    ticket = await load_visible_ticket(session, ticket_id, user)
    return await _state(session, ticket, user)


@router.post(
    "",
    response_model=TicketFeedbackRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_feedback(
    ticket_id: uuid.UUID,
    payload: TicketFeedbackCreate,
    session: session_Dependency,
    customer: customer_dependency,
) -> TicketFeedbackRead:
    """Submit the one allowed feedback answer for the caller's resolved ticket.

    A ticket the caller does not own is a ``404``; a resolved-only rule and the
    single-answer rule are both ``409``.
    """
    ticket = await load_visible_ticket(session, ticket_id, customer)

    if not is_feedback_eligible(ticket):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feedback is only available once the ticket is resolved",
        )
    if not can_submit_feedback(ticket, customer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot submit feedback for this ticket",
        )

    feedback = await submit_feedback(
        session,
        ticket=ticket,
        customer=customer,
        rating=payload.rating,
        comment=payload.comment,
    )
    await session.commit()
    await session.refresh(feedback)
    return TicketFeedbackRead.model_validate(feedback)
