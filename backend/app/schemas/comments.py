import uuid
from datetime import datetime

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel


class CommentCreate(SQLModel):
    body: str = Field(min_length=1, max_length=10000)


class InternalCommentCreate(SQLModel):
    body: str = Field(min_length=1, max_length=10000)
    is_internal: bool = True


class CommentRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    is_internal: bool
    created_at: datetime
    updated_at: datetime | None


class PublicCommentRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime | None