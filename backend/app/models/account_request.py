"""Account-management (admin escalation) requests.

An AGENT or ADMIN asks authorized ADMIN/OWNER staff to perform a privileged
account action they may not perform themselves (account recovery, identity
relinking, protected profile correction, role/status changes).

Design notes
------------
* The request stores *snapshots* of the target's permitted display fields at
  creation time so the decision is auditable even if the account later changes.
* This workflow never accepts or performs an arbitrary identity change: there
  is no field for a new ``clerk_id``, no field for a new local primary key, and
  the decision endpoints only move the request through its lifecycle. Identity
  changes must go through the supported Clerk verification flow separately.
* ``target_user_id`` is resolved server-side from trusted records (the related
  ticket's requester, or an admin-selected directory entry); a client-supplied
  id is validated to exist and never treated as proof of identity.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index, Text, func, text
from sqlmodel import Field, SQLModel

from app.enums.enums import EscalationCategory, EscalationStatus


class AccountManagementRequest(SQLModel, table=True):
    __tablename__ = "account_management_requests"
    __table_args__ = (
        Index("ix_account_management_requests_target_user_id", "target_user_id"),
        Index(
            "ix_account_management_requests_created_by_user_id", "created_by_user_id"
        ),
        Index("ix_account_management_requests_status", "status"),
        Index("ix_account_management_requests_ticket_id", "ticket_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # The local HelpDesk account the request is about. Resolved from trusted
    # records server-side; never used to execute an arbitrary change.
    target_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    target_full_name_snapshot: str = Field(max_length=120, nullable=False)
    target_email_snapshot: str = Field(max_length=255, nullable=False)

    # Optional related ticket that surfaced the problem.
    ticket_id: uuid.UUID | None = Field(default=None, foreign_key="tickets.id")

    category: EscalationCategory = Field(nullable=False)
    # Explicit ``Text`` matches the migration DDL exactly (see comment.py).
    justification: str = Field(nullable=False, sa_type=Text)
    internal_details: str | None = Field(default=None, nullable=True, sa_type=Text)

    status: EscalationStatus = Field(
        default=EscalationStatus.PENDING,
        nullable=False,
        sa_column_kwargs={"server_default": text("'PENDING'")},
    )

    # Decision audit. A rejection must always carry a reason; approvals and
    # completions may add one.
    decision_reason: str | None = Field(default=None, max_length=2000)
    decided_by_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    decided_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    completed_by_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    created_by_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )


class AccountRequestComment(SQLModel, table=True):
    """A comment on an escalation request.

    Visible to the request's creator and to authorized ADMIN/OWNER staff.
    Internal by nature: never returned by any customer-facing endpoint.
    """

    __tablename__ = "account_management_request_comments"
    __table_args__ = (
        CheckConstraint(
            "length(body) > 0",
            name="ck_account_request_comments_body_nonempty",
        ),
        Index("ix_account_management_request_comments_request_id", "request_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_id: uuid.UUID = Field(
        foreign_key="account_management_requests.id", nullable=False
    )
    author_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    # Explicit ``Text`` matches the migration DDL exactly (see comment.py).
    body: str = Field(nullable=False, sa_type=Text)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )


class AccountRequestEvent(SQLModel, table=True):
    """Append-only audit trail for an escalation request.

    Mirrors ``ticket_history``: JSON snapshots of the before/after value of
    whatever changed (status, decision, ...).
    """

    __tablename__ = "account_management_request_events"
    __table_args__ = (
        Index("ix_account_management_request_events_request_id", "request_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_id: uuid.UUID = Field(
        foreign_key="account_management_requests.id", nullable=False
    )
    actor_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    event_type: str = Field(max_length=40, nullable=False)
    old_value: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    new_value: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
