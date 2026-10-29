import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict, Field
from sqlmodel import SQLModel

MAX_FEEDBACK_COMMENT_LENGTH = 2_000


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


FeedbackComment = Annotated[
    str | None,
    BeforeValidator(_blank_to_none),
    Field(max_length=MAX_FEEDBACK_COMMENT_LENGTH),
]


class TicketFeedbackCreate(SQLModel):
    """The customer's feedback for a resolved ticket.

    ``ticket_id`` and ``customer_user_id`` are deliberately absent: they come
    from the path and the authenticated user, never from the body.
    """

    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    comment: FeedbackComment = None


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
