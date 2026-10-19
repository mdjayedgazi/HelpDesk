from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

# Importing the models package registers every table on SQLModel.metadata.
# Without this, create_all() would not know about any of our tables.
import app.models  # noqa: F401  (imported for its side effect)


def _normalize_database_url(url: str) -> str:
    """Return a database URL for an async driver that is actually installed.

    The project depends on ``psycopg`` (v3), not ``asyncpg``. A URL that still
    says ``postgresql+asyncpg`` would fail at import time because that driver is
    missing, so we transparently switch it to the psycopg async dialect.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_database_url(settings.DATABASE_URL)

# SQLite (used by the tests) needs this extra argument; PostgreSQL does not
# accept it, so only pass it when we really talk to SQLite.
_connect_args: dict[str, object] = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    connect_args=_connect_args,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


session_Dependency = Annotated[AsyncSession, Depends(get_db)]


async def create_session_and_tables() -> None:
    """Create any missing tables.

    Only used when AUTO_CREATE_TABLES is enabled or by the tests. Production
    databases should be created through a migration tool instead.
    """
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
