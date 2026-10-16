import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel

class AttachmentRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime