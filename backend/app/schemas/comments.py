import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict
from sqlmodel import Field, SQLModel

MAX_COMMENT_LENGTH = 10_000


def _stripped(value: object) -> object:
    """Trim before validation so a whitespace-only body cannot pass."""
    if isinstance(value, str):
        return value.strip()
    return value


TrimmedText = Annotated[str, BeforeValidator(_stripped)]


class CommentCreate(SQLModel):
    """A comment on a ticket.

    ``is_internal`` marks an internal note (staff only). Customers may send
    the field only when it is ``False``; the router rejects ``True`` for them.
    """

    model_config = ConfigDict(extra="forbid")

    body: TrimmedText = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)
    is_internal: bool = False


class CommentRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    is_internal: bool
    created_at: datetime
    updated_at: datetime | None


class PublicCommentRead(SQLModel):
    """Comment shape shown to customers: internal notes are never included."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime | None
