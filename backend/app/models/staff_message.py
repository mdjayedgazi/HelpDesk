"""Private staff-to-Owner messaging.

These tables are intentionally separate from ``comments``:

* a ``Comment`` always belongs to a ticket and can be public, while a staff
  conversation has no ticket and must never appear in any customer-facing
  response;
* authorization here is conversation-scoped (participant-based), not
  ticket-scoped.

The pair (``staff_user_id``, ``owner_user_id``) is unique, so each staff member
has exactly one thread with the single Owner. Both columns carry a foreign key
to ``users.id``; role checks happen in the application layer on every request
(the local database role is the source of truth).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func
from sqlmodel import Field, SQLModel


class StaffConversation(SQLModel, table=True):
    __tablename__ = "staff_conversations"
    __table_args__ = (
        # One thread per staff member (the Owner is unique in this app), which
        # makes the inbox unambiguous and prevents duplicate threads.
        Index("uq_staff_conversations_staff_user", "staff_user_id", unique=True),
        Index("ix_staff_conversations_owner_user_id", "owner_user_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    # The AGENT/ADMIN participant who initiated the conversation.
    staff_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    # The OWNER participant. Only a user holding the OWNER role may be set here
    # (enforced by the service, not by the client).
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    subject: str = Field(max_length=180, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
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
        CheckConstraint(
            "length(body) > 0", name="ck_staff_messages_body_nonempty"
        ),
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
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    # Set when the *recipient* (the other participant) reads the message.
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
