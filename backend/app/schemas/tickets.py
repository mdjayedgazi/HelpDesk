import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, ConfigDict, StringConstraints, field_validator
from sqlmodel import Field, SQLModel

from app.enums.enums import (
    ImpactLevel,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)

# A permissive but sane phone format: an optional leading "+", a first digit,
# then digits with the usual separators, ending in a digit (5-32 characters).
# The value is optional everywhere and is only ever returned by the staff-only
# contact endpoint.
PHONE_PATTERN = r"^\+?[0-9][0-9\s().\-]{3,28}[0-9]$"


def _stripped(value: object) -> object:
    """Trim surrounding whitespace before validation runs.

    Stripping happens *before* the length constraints so a whitespace-only
    value can never satisfy ``min_length=1``.
    """
    if isinstance(value, str):
        return value.strip()
    return value


def _blank_phone_to_none(value: object) -> object:
    """Treat an empty/whitespace-only phone as "not provided"."""
    if isinstance(value, str):
        return value.strip() or None
    return value


TrimmedText = Annotated[str, BeforeValidator(_stripped)]

# A validated phone number: digits with the usual separators, 5-32 characters.
PhoneNumber = Annotated[
    str,
    StringConstraints(max_length=32, pattern=PHONE_PATTERN),
]


class TicketCreate(SQLModel):
    """A customer opens a ticket with the details we need to help them.

    The owner, status, priority and ticket number are all decided by the
    server, never by the client: ``impact`` is the only urgency input and it is
    mapped to ``priority`` through the supported policy.
    """

    model_config = ConfigDict(extra="forbid")

    title: TrimmedText = Field(min_length=1, max_length=180)
    description: TrimmedText = Field(min_length=1)
    category: TicketCategory
    impact: ImpactLevel | None = None
    # Optional personal contact number. Never required, never echoed back in
    # public ticket responses.
    contact_phone: PhoneNumber | None = Field(default=None)

    @field_validator("contact_phone", mode="before")
    @classmethod
    def _normalize_phone(cls, value: object) -> object:
        return _blank_phone_to_none(value)


class TicketStaffUpdate(SQLModel):
    """Fields an agent or admin may edit on a ticket.

    Assignment is deliberately not here; use POST /tickets/{id}/assign.
    """

    model_config = ConfigDict(extra="forbid")

    title: TrimmedText | None = Field(default=None, min_length=1, max_length=180)
    description: TrimmedText | None = Field(default=None, min_length=1)
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    category: TicketCategory | None = None
    contact_phone: PhoneNumber | None = None

    @field_validator("contact_phone", mode="before")
    @classmethod
    def _normalize_phone(cls, value: object) -> object:
        return _blank_phone_to_none(value)


class TicketAssign(SQLModel):
    model_config = ConfigDict(extra="forbid")

    assignee_user_id: uuid.UUID | None = None


class TicketRead(SQLModel):
    """Public/customer ticket shape. Deliberately excludes ``contact_phone``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_number: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: TicketCategory
    created_by_user_id: uuid.UUID
    assignee_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    assigned_at: datetime | None
    resolved_at: datetime | None


class TicketContactRead(SQLModel):
    """Staff-only view of the optional contact number.

    Returned only to staff authorized to work on the ticket (the assignee, the
    unassigned queue, or an administrator), never to the requesting customer
    through a public response.
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: uuid.UUID
    contact_phone: str | None
