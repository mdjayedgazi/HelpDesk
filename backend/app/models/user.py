
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, func, text, CheckConstraint, Index, Sequence
from sqlmodel import Field, SQLModel, Relationship
from app.enums.enums import Role


class User(SQLModel, table=True):
    __tablename__ = 'users'
    __table_args__ = (
        CheckConstraint('email = lower(email)', name='ck_users_email_lowercase')
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    full_name: str = Field(
        max_length=120,
        nullable=False,
    )

    username: str = Field(
        max_length=90,
        unique=True,
        index=True,
        nullable=False,
    )

    email: str = Field(
        max_length=255,
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: str = Field(
        max_length=255,
        nullable=False,
    )

    role: Role = Field(
        default=Role.CUSTOMER,
        nullable=False,
        sa_column_kwargs={
            'server_default': text("'CUSTOMER'"),
        },
    )

    is_active: bool = Field(
        default=True,
        nullable=False,
        sa_column_kwargs={
            'server_default': text('true'),
        },
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={
            'server_default': func.now(),
        },
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={
            'server_default': func.now(),
            'onupdate': func.now(),
        },
    )

    created_tickets: list["Ticket"] = Relationship(
        back_populates="created_by",
        sa_relationship_kwargs={"foreign_keys": "Ticket.created_by_user_id"},
    )
    assigned_tickets: list["Ticket"] = Relationship(
        back_populates="assignee",
        sa_relationship_kwargs={"foreign_keys": "Ticket.assignee_user_id"},
    )
    comments: list["Comment"] = Relationship(back_populates="author")
    history_events: list["TicketHistory"] = Relationship(back_populates="actor")
    attachments: list["Attachment"] = Relationship(back_populates="uploaded_by")
    notifications: list["Notification"] = Relationship(back_populates="recipient")


