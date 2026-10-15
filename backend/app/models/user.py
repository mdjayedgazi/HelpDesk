
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, func, text
from sqlmodel import Field, SQLModel


class Role(str, Enum):
    CUSTOMER = 'CUSTOMER'
    ADMIN = 'ADMIN'
    AGENT = 'AGENT'


class User(SQLModel, table=True):
    __tablename__ = 'users'

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )

    full_name: str = Field(
        max_length=120,
        nullable=False,
    )

    username: str = Field(
        max_length=90,
        unique=True,
        index=True,
        nullable=False,
    )

    email: str = Field(
        max_length=255,
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: str = Field(
        max_length=255,
        nullable=False,
    )

    role: Role = Field(
        default=Role.CUSTOMER,
        nullable=False,
        sa_column_kwargs={
            'server_default': text("'CUSTOMER'"),
        },
    )

    is_active: bool = Field(
        default=True,
        nullable=False,
        sa_column_kwargs={
            'server_default': text('true'),
        },
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={
            'server_default': func.now(),
        },
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={
            'server_default': func.now(),
            'onupdate': func.now(),
        },
    )
