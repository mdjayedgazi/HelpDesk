import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Text, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.models.ticket import Ticket
from app.models.user import User

class Comment(SQLModel, table=True):
    __tablename__ = "comments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id", index=True, nullable=False)
    author_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    # ``sa_type=Text`` keeps the model metadata identical to the migration
    # DDL (``sa.Text``) so ``alembic check`` reports no spurious type drift.
    body: str = Field(nullable=False, sa_type=Text)
    is_internal: bool = Field(
        default=False,
        nullable=False,
        sa_column_kwargs={"server_default": text("false")},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    ticket: Ticket = Relationship(back_populates="comments")
    author: User = Relationship(back_populates="comments")