import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlmodel import Field, Relationship, SQLModel

from app.models.ticket import Ticket
from app.models.user import User


class TicketHistory(SQLModel, table=True):
    __tablename__ = "ticket_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id", index=True, nullable=False)
    actor_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    event_type: str = Field(max_length=40, nullable=False)
    old_value: dict | None = Field(default=None, sa_type=None)
    new_value: dict | None = Field(default=None, sa_type=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )

    ticket: Ticket = Relationship(back_populates="history")
    actor: User = Relationship(back_populates="history_events")