import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel

class TicketHistoryRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    actor_user_id: uuid.UUID
    event_type: str
    old_value: dict | None
    new_value: dict | None
    created_at: datetime