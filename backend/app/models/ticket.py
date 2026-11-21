import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, Text, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.enums.enums import TicketCategory, TicketPriority, TicketStatus
from app.models.user import User

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.comment import Comment
    from app.models.notification import Notification
    from app.models.ticketHistory import TicketHistory


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_created_by_user_id", "created_by_user_id"),
        Index("ix_tickets_assignee_user_id", "assignee_user_id"),
        # Every ticket list orders by created_at (newest first) with
        # LIMIT/OFFSET. The single-column role indexes cannot serve that
        # ordering, so this one covers the default listing and pagination.
        Index("ix_tickets_created_at", "created_at"),
        # Optional client-supplied idempotency key, unique per creator. A
        # retried or double-submitted create returns the original ticket
        # instead of opening a duplicate. NULL keys (the default) are excluded
        # from the constraint.
        Index(
            "uq_tickets_creator_request_key",
            "created_by_user_id",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
            sqlite_where=text("client_request_id IS NOT NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Human-friendly sequential number. It is assigned in the ticket service
    # (see app.services.tickets) so that it works on both PostgreSQL and the
    # SQLite database used by the tests. The unique index protects us from
    # duplicates if two requests ever race; the column is NOT NULL because the
    # API contract and every creation path require it.
    ticket_number: int = Field(
        unique=True,
        index=True,
        nullable=False,
    )
    # Optional client-supplied idempotency key for the create request. Paired
    # with ``created_by_user_id`` in a partial unique index so a retried or
    # double-submitted create returns the original ticket instead of a
    # duplicate. It is never exposed by the response schemas.
    client_request_id: str | None = Field(default=None, max_length=100, nullable=True)
    title: str = Field(max_length=180, nullable=False)
    # Explicit ``Text`` matches the migration DDL exactly (see comment.py).
    description: str = Field(nullable=False, sa_type=Text)
    status: TicketStatus = Field(
        default=TicketStatus.OPEN,
        nullable=False,
        sa_column_kwargs={"server_default": text("'OPEN'")},
    )
    priority: TicketPriority = Field(
        default=TicketPriority.NORMAL,
        nullable=False,
        sa_column_kwargs={"server_default": text("'NORMAL'")},
    )
    # Customer-chosen issue category. The server default keeps rows created
    # before categories existed readable; the API requires a category for every
    # new ticket.
    category: TicketCategory = Field(
        default=TicketCategory.OTHER,
        nullable=False,
        sa_column_kwargs={"server_default": text("'OTHER'")},
    )
    # Optional customer contact number. Personal information: never returned by
    # the public/customer ticket schemas; only staff authorized to work on the
    # ticket can read it (see the router's staff-only contact endpoint).
    contact_phone: str | None = Field(default=None, max_length=32, nullable=True)
    created_by_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    assignee_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    # Set whenever the ticket becomes assigned and cleared on unassign. Used by
    # the workload-aware assignment service for its deterministic fairness
    # tie-break (oldest last assignment wins) and shown in the staff details.
    assigned_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
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
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    created_by: User = Relationship(
        back_populates="created_tickets",
        sa_relationship_kwargs={"foreign_keys": "Ticket.created_by_user_id"},
    )
    assignee: User | None = Relationship(
        back_populates="assigned_tickets",
        sa_relationship_kwargs={"foreign_keys": "Ticket.assignee_user_id"},
    )
    comments: list["Comment"] = Relationship(back_populates="ticket")
    history: list["TicketHistory"] = Relationship(back_populates="ticket")
    attachments: list["Attachment"] = Relationship(back_populates="ticket")
    notifications: list["Notification"] = Relationship(back_populates="related_ticket")
