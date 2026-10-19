import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.enums.enums import Role

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.comment import Comment
    from app.models.notification import Notification
    from app.models.ticket import Ticket
    from app.models.ticketHistory import TicketHistory


class User(SQLModel, table=True):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "email = lower(email)",
            name="ck_users_email_lowercase",
        ),
        # At most one OWNER may exist. This partial unique index is the database
        # half of the "single, permanent Owner" rule; the bootstrap command and
        # the user-management endpoints enforce it transactionally on top.
        Index(
            "uq_users_single_owner",
            "role",
            unique=True,
            postgresql_where=text("role = 'OWNER'"),
            sqlite_where=text("role = 'OWNER'"),
        ),
    )

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    clerk_id: str | None = Field(
        default=None,
        max_length=255,
        unique=True,
        index=True,
        nullable=True,
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

    # Clerk-hosted profile image URL (``user.image_url``). Clerk is the source
    # of truth; this cached copy lets the app render other users' photos
    # (comments, conversations, staff tables) without exposing the Clerk secret.
    # Only ever written from verified Clerk data server-side.
    image_url: str | None = Field(
        default=None,
        max_length=512,
        nullable=True,
    )

    # Clerk manages passwords. Keep this nullable during migration
    # so newly provisioned users don't need a local password hash.
    password_hash: str | None = Field(
        default=None,
        max_length=255,
        nullable=True,
    )

    role: Role = Field(
        default=Role.CUSTOMER,
        nullable=False,
        sa_column_kwargs={
            "server_default": text("'CUSTOMER'"),
        },
    )

    is_active: bool = Field(
        default=True,
        nullable=False,
        sa_column_kwargs={
            "server_default": text("true"),
        },
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={
            "server_default": func.now(),
        },
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
        },
    )

    created_tickets: list["Ticket"] = Relationship(
        back_populates="created_by",
        sa_relationship_kwargs={
            "foreign_keys": "Ticket.created_by_user_id",
        },
    )

    assigned_tickets: list["Ticket"] = Relationship(
        back_populates="assignee",
        sa_relationship_kwargs={
            "foreign_keys": "Ticket.assignee_user_id",
        },
    )

    comments: list["Comment"] = Relationship(
        back_populates="author",
    )

    history_events: list["TicketHistory"] = Relationship(
        back_populates="actor",
    )

    attachments: list["Attachment"] = Relationship(
        back_populates="uploaded_by",
    )

    notifications: list["Notification"] = Relationship(
        back_populates="recipient",
    )