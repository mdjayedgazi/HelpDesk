import uuid
from datetime import datetime

from pydantic import ConfigDict, EmailStr
from sqlmodel import Field, SQLModel

from app.enums.enums import Role


class UserUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    username: str | None = Field(default=None, min_length=2, max_length=90)
    email: EmailStr | None = None


class UserAdminUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    username: str | None = Field(default=None, min_length=2, max_length=90)
    email: EmailStr | None = None
    role: Role | None = None
    is_active: bool | None = None


class UserRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    username: str
    email: EmailStr
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime