"""Liveness and dependency readiness checks for the API.

Liveness only proves the process can answer HTTP. Readiness checks the services
the application cannot operate without. Details are intentionally coarse: no
connection string, host, exception text, or vendor error is returned to the
caller.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.rate_limit import ping_rate_limit_store

logger = logging.getLogger(__name__)

# Neon's pooled endpoint can need several seconds to establish the first
# connection after the database or the Railway service wakes from idle. The
# probe must not report a healthy deployment as unavailable during that window;
# Railway's own healthcheck timeout is much larger (default 300s).
_CHECK_TIMEOUT_SECONDS = 10.0


async def _database_check() -> str:
    async with asyncio.timeout(_CHECK_TIMEOUT_SECONDS):
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    return "ok"


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
        else:
            statuses[name] = result
            if result == "error":
                healthy = False
    return healthy, statuses
