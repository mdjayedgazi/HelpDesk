"""Universal staff-to-staff private messaging.

These tables are intentionally separate from ``comments``:

* a ``Comment`` always belongs to a ticket and can be public, while a staff
  conversation has no ticket and must never appear in any customer-facing
  response;
* authorization here is conversation-scoped (participant-based), not
  ticket-scoped.

A conversation is a 1:1 thread between any two eligible staff members. The two
participants are stored in a **canonical order** (the smaller UUID first) by the
service layer, and a unique index on the ordered pair guarantees there is
exactly one thread per pair no matter who starts it. This replaces the original
hard-wired staff <-> Owner pair, which made owner-only messaging the only
possible topology.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


class StaffConversation(SQLModel, table=True):
    __tablename__ = "staff_conversations"
    __table_args__ = (
        # Exactly one thread per participant pair. The service always writes the
        # pair in canonical order (participant_a_id < participant_b_id), so this
        # is a true uniqueness guarantee rather than a duplicate-per-direction
        # one. It is also the idempotency key for "start a conversation".
        UniqueConstraint(
            "participant_a_id",
            "participant_b_id",
            name="uq_staff_conversations_participant_pair",
        ),
        # A row cannot name the same person twice; a self-conversation is
        # meaningless and would break the canonical-pair guarantee.
        CheckConstraint(
            "participant_a_id <> participant_b_id",
            name="ck_staff_conversations_distinct_participants",
        ),
        Index("ix_staff_conversations_participant_a", "participant_a_id"),
        Index("ix_staff_conversations_participant_b", "participant_b_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # The two participants, in canonical (ascending UUID) order. Both must hold
    # an internal staff role (AGENT/ADMIN/OWNER); that is enforced by the
    # service on every create, not by the database.
    participant_a_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    participant_b_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    subject: str = Field(max_length=180, nullable=False)
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
    last_message_at: datetime | None = Field(
        default=None, sa_type=DateTime(timezone=True)
    )


class StaffMessage(SQLModel, table=True):
    __tablename__ = "staff_messages"
    __table_args__ = (
        CheckConstraint("length(body) > 0", name="ck_staff_messages_body_nonempty"),
        Index("ix_staff_messages_conversation_id", "conversation_id"),
        Index("ix_staff_messages_sender_user_id", "sender_user_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="staff_conversations.id", nullable=False
    )
    sender_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    # Explicit ``Text`` matches the migration DDL exactly (see comment.py).
    body: str = Field(nullable=False, sa_type=Text)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    # Set when *a participant other than the sender* reads the message.
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class StaffMessageMention(SQLModel, table=True):
    """A structured @mention on a staff message.

    The mention is tied to a real ``users.id``; the message body keeps the
    human-readable ``@Name`` text, but correctness never depends on parsing it.
    One row per (message, mentioned user) so mentioning the same person twice in
    one message is stored once (and notified once).
    """

    __tablename__ = "staff_message_mentions"
    __table_args__ = (
        UniqueConstraint(
            "message_id",
            "mentioned_user_id",
            name="uq_staff_message_mentions_message_user",
        ),
        Index("ix_staff_message_mentions_message_id", "message_id"),
        Index("ix_staff_message_mentions_mentioned_user_id", "mentioned_user_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="staff_messages.id", nullable=False)
    mentioned_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
