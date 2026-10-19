"""Schemas for the Owner Inbox internal-messaging endpoints.

The Owner composes messages to an audience (everyone / all agents / all admins
/ one employee) and reads the sent folder; addressed recipients may list the
messages sent to them and mark them read. The sender is never accepted from a
request body - it is always the authenticated user - so every input schema uses
``extra="forbid"``.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict, model_validator
from sqlmodel import Field, SQLModel

from app.enums.enums import InternalAudience, Role

# Maximum lengths, validated on input. The body is additionally protected by a
# database CHECK that rejects empty values.
MAX_SUBJECT_LENGTH = 180
MAX_BODY_LENGTH = 5000


def _stripped(value: object) -> object:
    """Trim whitespace *before* length validation runs.

    This is what makes a whitespace-only subject or body invalid: the stripped
    value is what the ``min_length`` constraint sees.
    """
    if isinstance(value, str):
        return value.strip()
    return value


TrimmedText = Annotated[str, BeforeValidator(_stripped)]


class InternalMessageCreate(SQLModel):
    """The Owner's compose payload.

    ``recipient_user_id`` is required for (and only allowed with) the
    ``individual`` audience; the id is validated to exist, be active and be an
    AGENT/ADMIN account by the service before anything is stored.
    """

    model_config = ConfigDict(extra="forbid")

    audience: InternalAudience
    subject: TrimmedText = Field(min_length=1, max_length=MAX_SUBJECT_LENGTH)
    body: TrimmedText = Field(min_length=1, max_length=MAX_BODY_LENGTH)
    recipient_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check_recipient_matches_audience(self) -> "InternalMessageCreate":
        if (
            self.audience == InternalAudience.INDIVIDUAL
            and self.recipient_user_id is None
        ):
            raise ValueError(
                "recipient_user_id is required when audience is 'individual'"
            )
        if (
            self.audience != InternalAudience.INDIVIDUAL
            and self.recipient_user_id is not None
        ):
            raise ValueError(
                "recipient_user_id may only be set for an individual message"
            )
        return self


class InternalMessageRecipientRead(SQLModel):
    """An addressed recipient, with the identity snapshot taken at send time."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_user_id: uuid.UUID
    recipient_role_snapshot: Role
    recipient_full_name_snapshot: str
    recipient_email_snapshot: str
    read_at: datetime | None


class InternalMessageSummary(SQLModel):
    """A row in the Owner's sent list."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sender_user_id: uuid.UUID
    audience: InternalAudience
    subject: str
    # Body preview, kept short so the list stays lightweight.
    preview: str
    recipient_count: int
    # How many addressed recipients have actually opened the message. Read
    # state is real (tracked per recipient); delivery is never claimed.
    read_count: int
    created_at: datetime


class InternalMessageDetail(SQLModel):
    """One sent message with its full body and (paginated) recipient list."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sender_user_id: uuid.UUID
    audience: InternalAudience
    subject: str
    body: str
    recipient_count: int
    read_count: int
    created_at: datetime
    # Total number of recipient rows; ``recipients`` may be a page of them.
    recipient_total: int
    recipients: list[InternalMessageRecipientRead]


class InternalMessageReceived(SQLModel):
    """A message addressed to the requesting recipient (their own row only)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    sender_user_id: uuid.UUID
    sender_full_name: str
    audience: InternalAudience
    subject: str
    body: str
    created_at: datetime
    read_at: datetime | None
