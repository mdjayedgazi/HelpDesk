"""Alembic migration environment.

This wires Alembic to the same async database URL and the same model metadata
that the application uses, so migrations describe the real schema:

* the URL comes from ``settings.DATABASE_URL`` (normalised to the installed
  async driver), never from a hard-coded value,
* importing ``app.models`` registers every table on ``SQLModel.metadata``.

Offline mode (``alembic upgrade head --sql``) only renders SQL and never opens
a connection, which makes it safe to review migrations without a database.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

# Importing the models package registers every table on SQLModel.metadata.
import app.models  # noqa: F401  (imported for its side effect)
from app.core.config import settings
from app.core.database import _normalize_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the metadata Alembic compares against / autogenerates from.
target_metadata = SQLModel.metadata


def _database_url() -> str:
    return _normalize_database_url(settings.DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no connection)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
