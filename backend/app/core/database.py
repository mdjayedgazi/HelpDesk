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

# Importing the models package registers every table on SQLModel.metadata.
# Without this, create_all() would not know about any of our tables.
import app.models  # noqa: F401  (imported for its side effect)
from app.core.config import settings


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

# SQLite (used by the tests) needs its own connection arguments and does not
# accept the PostgreSQL pool options. PostgreSQL gets explicit connect and
# pool settings so a stalled database cannot hold every request forever.
_engine_kwargs: dict[str, object] = {}
_connect_args: dict[str, object] = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
else:
    _connect_args["connect_timeout"] = settings.DB_CONNECT_TIMEOUT_SECONDS
    _engine_kwargs.update(
        pool_pre_ping=True,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    )

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    connect_args=_connect_args,
    **_engine_kwargs,
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
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
