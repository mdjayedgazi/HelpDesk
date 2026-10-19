"""Schemas for account-management (admin escalation) requests.

An AGENT (or ADMIN) uses this workflow to ask authorized ADMIN/OWNER staff for
a privileged account action. There is deliberately no field for a new Clerk id,
a new local primary key, an email, or a role: a request describes *why* someone
needs help, and any resulting identity change is performed through the
supported, audited process - never through this API.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict, field_validator
from sqlmodel import Field, SQLModel

from app.enums.enums import EscalationCategory, EscalationStatus

# Maximum length for free-text fields of a request or comment.
MAX_JUSTIFICATION_LENGTH = 4000
MAX_COMMENT_LENGTH = 4000
MAX_REASON_LENGTH = 2000


def _stripped(value: object) -> object:
    """Trim surrounding whitespace before length validation runs.

    Stripping happens *before* the field constraints so a whitespace-only
    value can never satisfy ``min_length=1``.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


TrimmedText = Annotated[str, BeforeValidator(_stripped)]


class AccountRequestCreate(SQLModel):
    """Open an account-management request for review.

    The target account is derived from trusted records server-side:

    * an AGENT must reference a ticket they can see; the target is the ticket
      requester;
    * an ADMIN may additionally pass ``target_user_id`` from the directory,
      which is validated but never treated as proof of identity.

    ``title``/``status``/``created_by_user_id``/snapshots are all decided by
    the server, never by the client.
    """

    model_config = ConfigDict(extra="forbid")

    category: EscalationCategory
    justification: TrimmedText = Field(min_length=1, max_length=MAX_JUSTIFICATION_LENGTH)
    internal_details: TrimmedText | None = Field(
        default=None, max_length=MAX_JUSTIFICATION_LENGTH
    )
    # The related ticket that surfaced the problem. Required for agents.
    ticket_id: uuid.UUID | None = None
    # Admin-only convenience for requests not tied to a ticket. Agents may only
    # repeat the ticket's requester here; anything else is rejected.
    target_user_id: uuid.UUID | None = None


class AccountRequestStatusUpdate(SQLModel):
    """A reviewer moves a request through its lifecycle.

    ``reason`` is mandatory for a rejection and optional (but recorded) for
    every other decision. The actor is always taken from the session.
    """

    model_config = ConfigDict(extra="forbid")

    status: EscalationStatus
    reason: TrimmedText | None = Field(default=None, max_length=MAX_REASON_LENGTH)

    @field_validator("reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: object) -> object:
        return _blank_to_none(value)


class AccountRequestCommentCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    body: TrimmedText = Field(min_length=1, max_length=MAX_COMMENT_LENGTH)


class AccountRequestCommentRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime


class AccountRequestEventRead(SQLModel):
    """One entry of the append-only request audit trail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: uuid.UUID
    actor_user_id: uuid.UUID
    event_type: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime


class AccountRequestRead(SQLModel):
    """Request summary and detail without comments/events."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_user_id: uuid.UUID
    target_full_name_snapshot: str
    target_email_snapshot: str
    ticket_id: uuid.UUID | None
    category: EscalationCategory
    justification: str
    internal_details: str | None
    status: EscalationStatus
    decision_reason: str | None
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None
    completed_by_user_id: uuid.UUID | None
    completed_at: datetime | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AccountRequestDetail(SQLModel):
    model_config = ConfigDict(extra="forbid")

    request: AccountRequestRead
    comments: list[AccountRequestCommentRead]
    events: list[AccountRequestEventRead]
