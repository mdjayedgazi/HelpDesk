import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel


class TicketFeedbackCreate(SQLModel):
    """The customer's feedback for a resolved ticket.

    ``ticket_id`` and ``customer_user_id`` are deliberately absent: they come
    from the path and the authenticated user, never from the body.
    """

    model_config = ConfigDict(extra="forbid")

    rating: int
    comment: str | None = None


class TicketFeedbackRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    customer_user_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime


class TicketFeedbackState(SQLModel):
    """What the current viewer may see and do for a ticket's feedback.

    ``can_submit`` is computed server-side (the ticket's own customer, ticket
    resolved, no feedback yet) so the client renders the form only when the
    backend would actually accept the submission.
    """

    feedback: TicketFeedbackRead | None = None
    can_submit: bool = False
    # True when the ticket is in a state where feedback is expected but the
    # customer has not answered yet (drives the "share feedback" prompt).
    awaiting_feedback: bool = False
