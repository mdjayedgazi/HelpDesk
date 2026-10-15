import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Sequence, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.enums.enums import TicketStatus, TicketPriority
from app.models.user import User



class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_created_by_user_id", "created_by_user_id"),
        Index("ix_tickets_assignee_user_id", "assignee_user_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_number: int | None = Field(
        default=None,
        sa_column_kwargs={"server_default": Sequence("ticket_number_seq", start=10001).next_value()},
        unique=True,
        index=True,
    )
    title: str = Field(max_length=180, nullable=False)
    description: str = Field(nullable=False)
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
    created_by_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    assignee_user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
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