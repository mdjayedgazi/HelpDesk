"""Schemas for the private staff <-> Owner messaging channel."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict, field_validator
from sqlmodel import Field, SQLModel

from app.enums.enums import Role

# Maximum length of one private staff message. Validated on input; the body is
# also protected by a database CHECK that rejects empty values.
MAX_MESSAGE_LENGTH = 5000
MAX_SUBJECT_LENGTH = 180


def _stripped(value: object) -> object:
    """Trim whitespace *before* length validation runs.

    This is what makes a whitespace-only body invalid: the stripped value is
    what the ``min_length`` constraint sees.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


TrimmedText = Annotated[str, BeforeValidator(_stripped)]


class StaffConversationCreate(SQLModel):
    """Start (or fetch) the caller's conversation with the Owner."""

    model_config = ConfigDict(extra="forbid")

    subject: TrimmedText | None = Field(
        default=None, min_length=1, max_length=MAX_SUBJECT_LENGTH
    )

    @field_validator("subject", mode="before")
    @classmethod
    def _normalize_subject(cls, value: object) -> object:
        return _blank_to_none(value)


class StaffMessageCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    body: TrimmedText = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class StaffMessageRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_user_id: uuid.UUID
    body: str
    created_at: datetime
    read_at: datetime | None


class StaffConversationRead(SQLModel):
    """A conversation summary for the inbox list."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    subject: str
    # Both participants, so a client can render "you / the Owner" without
    # inventing identities. The staff display name is included because agents
    # cannot read the user directory (that is ADMIN/OWNER-only).
    staff_user_id: uuid.UUID
    staff_full_name: str
    # The staff participant's application role, so the Owner inbox can show who
    # is an Administrator and who is an Agent (and filter by it).
    staff_role: Role | None = None
    # Cached Clerk profile images for the two participants, so the messaging UI
    # can render real avatars without exposing the Clerk secret. Null when the
    # participant has no Clerk-hosted image (e.g. imported demo records).
    staff_image_url: str | None = None
    owner_user_id: uuid.UUID
    owner_image_url: str | None = None
    created_at: datetime
    last_message_at: datetime | None
    message_count: int
    # Messages the *requesting* user has not read yet (addressed to them).
    unread_count: int
    last_message_preview: str | None
    last_message_sender_user_id: uuid.UUID | None
    # The most recent message *received* by the viewer (never one they wrote).
    # The Owner inbox lists messages "received from agents and administrators",
    # so it shows this instead of the latest activity in the thread.
    last_received_preview: str | None = None
    last_received_at: datetime | None = None


class StaffConversationDetail(SQLModel):
    model_config = ConfigDict(extra="forbid")

    conversation: StaffConversationRead
    messages: list[StaffMessageRead]


class MarkReadResult(SQLModel):
    model_config = ConfigDict(extra="forbid")

    updated: int
