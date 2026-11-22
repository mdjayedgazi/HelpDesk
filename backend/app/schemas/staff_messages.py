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
    """Start (or fetch) a 1:1 conversation with another staff member.

    ``recipient_user_id`` is the employee to talk to. The pair is unique, so a
    second call for the same two people returns the existing conversation.
    """

    model_config = ConfigDict(extra="forbid")

    recipient_user_id: uuid.UUID
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
    # Structured @mentions: real employee ids selected in the composer. The
    # backend validates each one; display-name text is never authoritative.
    # Capped so one message cannot fan out an unbounded number of rows.
    mentioned_user_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)

    @field_validator("mentioned_user_ids", mode="before")
    @classmethod
    def _default_mentions(cls, value: object) -> object:
        return value or []


class StaffMessageRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_user_id: uuid.UUID
    body: str
    created_at: datetime
    read_at: datetime | None
    # The employees this message mentions, so the client can render them as
    # distinguishable tokens without re-parsing the body.
    mentioned_user_ids: list[uuid.UUID] = Field(default_factory=list)


class StaffConversationRead(SQLModel):
    """A conversation summary for the inbox list."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    subject: str
    # The two participants (canonical order). Exposed so a client never has to
    # invent identities.
    participant_a_id: uuid.UUID
    participant_b_id: uuid.UUID
    # The *other* participant relative to the requesting viewer, resolved
    # server-side, so the conversation panel can render the counterpart without
    # needing the admin-only user directory.
    counterpart_user_id: uuid.UUID | None = None
    counterpart_full_name: str
    counterpart_role: Role | None = None
    counterpart_image_url: str | None = None
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
