"""Liveness and dependency readiness checks for the API.

Liveness only proves the process can answer HTTP. Readiness checks the services
the application cannot operate without. Details are intentionally coarse: no
connection string, host, exception text, or vendor error is returned to the
caller.

The ``schema`` check compares the live Alembic revision with the revision
shipped in this image and verifies that the core tables exist. It is a
production control: in development and test the schema may legitimately be
created from metadata (``AUTO_CREATE_TABLES``) without an ``alembic_version``
row, so a non-``ok`` schema is reported but does not fail the probe there.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.core.database import engine
from app.core.rate_limit import ping_rate_limit_store

logger = logging.getLogger(__name__)

# Neon's pooled endpoint can need several seconds to establish the first
# connection after the database or the Railway service wakes from idle. The
# probe must not report a healthy deployment as unavailable during that window;
# Railway's own healthcheck timeout is much larger (default 300s).
_CHECK_TIMEOUT_SECONDS = 10.0

# Core tables every supported deployment must have. Checking a handful of them
# is cheap and catches a partially applied or empty schema even when an
# ``alembic_version`` row happens to exist.
_REQUIRED_TABLES = (
    "users",
    "tickets",
    "comments",
    "notifications",
    "attachments",
    "alembic_version",
)

# ``app/core/health.py`` -> ``app/core`` -> ``app`` -> backend root (where
# ``alembic.ini`` lives, copied into the image at ``/app``).
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache(maxsize=1)
def expected_schema_revision() -> str | None:
    """Return the single Alembic head shipped with this image, or ``None``.

    Reading the script directory is filesystem-only and never opens a database
    connection. It is cached because the head cannot change while the process
    runs (migrations are applied before the new image serves traffic).
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI)))
        heads = script.get_heads()
    except Exception:  # noqa: BLE001 - readiness must never crash the probe
        logger.error("Could not read the Alembic migration head")
        return None

    if len(heads) != 1:
        logger.error("Alembic has %d heads; exactly one is required", len(heads))
        return None
    return heads[0]


def _missing_tables(connection) -> list[str]:
    """Return the required tables that do not exist (runs on a sync cursor)."""
    inspector = inspect(connection)
    return [table for table in _REQUIRED_TABLES if not inspector.has_table(table)]


async def schema_status(connection: AsyncConnection) -> str:
    """Return a coarse schema state for readiness.

    Values are intentionally non-diagnostic for public callers: ``ok``,
    ``outdated``, ``incomplete``, or ``unknown``. Operators get the precise
    category from the readiness log line, never from the HTTP response.
    """
    expected = expected_schema_revision()
    if expected is None:
        return "unknown"

    missing = await connection.run_sync(_missing_tables)
    if missing:
        logger.error("Readiness schema is missing tables: %s", ", ".join(missing))
        return "incomplete"

    result = await connection.execute(text("SELECT version_num FROM alembic_version"))
    current = result.scalar_one_or_none()
    if current == expected:
        return "ok"
    logger.error(
        "Readiness schema revision is %s, expected %s", current or "missing", expected
    )
    return "outdated" if current else "incomplete"


def schema_failure_is_fatal(status: str) -> bool:
    """Whether a non-``ok`` schema state must fail readiness.

    Production deployments are migration-managed, so a missing or outdated
    schema is not safe to serve. Development and test may create tables from
    metadata and have no ``alembic_version`` row, so the state is reported but
    not fatal there.
    """
    return settings.is_production and status != "ok"


async def _database_check() -> str:
    async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    return "ok"


async def _schema_check() -> str:
    async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
        async with engine.connect() as connection:
            return await schema_status(connection)


async def _redis_check() -> str:
    if not settings.RATE_LIMIT_ENABLED:
        return "disabled"
    async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
        await ping_rate_limit_store()
    return "ok"


async def _clamav_check() -> str:
    if not settings.MALWARE_SCAN_ENABLED:
        return "disabled"
    if not settings.CLAMAV_HOST:
        return "error"
    async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
        _reader, writer = await asyncio.open_connection(
            settings.CLAMAV_HOST,
            settings.CLAMAV_PORT,
        )
        writer.close()
        await writer.wait_closed()
    return "ok"


async def readiness() -> tuple[bool, dict[str, str]]:
    checks = {
        "database": _database_check,
        "schema": _schema_check,
        "redis": _redis_check,
        "clamav": _clamav_check,
    }
    results = await asyncio.gather(
        *(check() for check in checks.values()),
        return_exceptions=True,
    )
    statuses: dict[str, str] = {}
    healthy = True
    for name, result in zip(checks, results, strict=True):
        if isinstance(result, BaseException):
            # Log the failure category for operators; never include the
            # exception text (it can contain a host, port, or credential).
            logger.error(
                "Readiness check failed for %s (%s)", name, type(result).__name__
            )
            statuses[name] = "error"
            healthy = False
            continue

        statuses[name] = result
        if name == "schema":
            if schema_failure_is_fatal(result):
                healthy = False
        elif result == "error":
            healthy = False
    return healthy, statuses
