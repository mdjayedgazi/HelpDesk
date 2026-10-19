import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel
from app.enums.enums import NotificationType

class NotificationRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_user_id: uuid.UUID
    related_ticket_id: uuid.UUID | None
    # Present on private staff <-> Owner message notifications so the client
    # can deep-link into the conversation. Always ``None`` for customers.
    related_conversation_id: uuid.UUID | None = None
    type: NotificationType
    title: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationUpdate(SQLModel):
    """The only field a client may change on a notification."""

    model_config = ConfigDict(extra="forbid")

    is_read: bool