import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel

from app.enums.enums import TicketStatus, TicketPriority

class TicketCreate(SQLModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1)


class TicketUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, min_length=1)


class TicketStaffUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, min_length=1)
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assignee_user_id: uuid.UUID | None = None


class TicketRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_number: int
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    created_by_user_id: uuid.UUID
    assignee_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None