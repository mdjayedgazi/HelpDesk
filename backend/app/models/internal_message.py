"""Owner-composed internal messages (broadcasts and direct notes).

These tables are deliberately separate from ``staff_conversations`` /
``staff_messages`` (the 1:1 staff <-> Owner *thread*). They model the other
direction of internal communication that the Owner Inbox needs:

* a message the Owner sends to an *audience* (everyone, all agents, all admins,
  or one employee);
* a group message is stored **exactly once** and every addressed employee is
  recorded as its own recipient row, so the intended recipient list is
  preserved even if an employee's role changes later;
* per-recipient read state is tracked, which is what lets the Sent view report
  real read counts (never an invented "delivered" state).

Nothing here is customer-visible: the API only exposes a row to the Owner
(author / sent folder) and to each addressed recipient for their own row.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, SQLModel

from app.enums.enums import InternalAudience, Role


class InternalMessage(SQLModel, table=True):
    __tablename__ = "internal_messages"
    __table_args__ = (
        CheckConstraint(
            "length(subject) > 0", name="ck_internal_messages_subject_nonempty"
        ),
        CheckConstraint("length(body) > 0", name="ck_internal_messages_body_nonempty"),
        # A message is only ever created together with at least one recipient
        # row, so an empty audience can never be persisted.
        CheckConstraint(
            "recipient_count > 0",
            name="ck_internal_messages_recipient_count_positive",
        ),
        Index("ix_internal_messages_sender_user_id", "sender_user_id"),
        Index("ix_internal_messages_audience", "audience"),
        Index("ix_internal_messages_created_at", "created_at"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # The author. Only the Owner composes these messages (enforced by the API),
    # so in practice this is always the single OWNER account. The value is
    # always taken from the authenticated user, never from a request body.
    sender_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    audience: InternalAudience = Field(nullable=False)
    subject: str = Field(max_length=180, nullable=False)
    # Explicit ``Text`` matches the migration DDL exactly (see comment.py).
    body: str = Field(nullable=False, sa_type=Text)
    # Snapshot of how many recipients were addressed at send time. Kept in sync
    # with the recipient rows in the same transaction.
    recipient_count: int = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )


class InternalMessageRecipient(SQLModel, table=True):
    __tablename__ = "internal_message_recipients"
    __table_args__ = (
        # One row per (message, recipient): the unique constraint makes a
        # duplicated recipient impossible even under a retry.
        UniqueConstraint(
            "message_id",
            "recipient_user_id",
            name="uq_internal_message_recipients_message_user",
        ),
        Index("ix_internal_message_recipients_message_id", "message_id"),
        Index(
            "ix_internal_message_recipients_recipient_user_id",
            "recipient_user_id",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="internal_messages.id", nullable=False)
    recipient_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    # Snapshots so the intended recipient list is auditable even if the account
    # is later renamed, re-emailed or moved to another role. Only AGENT/ADMIN
    # accounts are ever recorded here.
    recipient_role_snapshot: Role = Field(nullable=False)
    recipient_full_name_snapshot: str = Field(max_length=120, nullable=False)
    recipient_email_snapshot: str = Field(max_length=255, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    # Set when the addressed recipient opens the message.
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
