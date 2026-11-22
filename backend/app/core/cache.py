"""Small, optional cache-aside layer over the existing Redis instance.

This module adds *read-through caching* for expensive, frequently requested read
endpoints. It reuses the same Redis deployment that already backs rate limiting,
so no new infrastructure is introduced.

Design principles
-----------------
* **Optional and safe.** Caching turns on only when ``CACHE_ENABLED`` is set and
  a Redis URL is configured. Any Redis error (down, timeout, wrong type) is
  treated as a cache **miss**: the caller reads PostgreSQL and the request still
  succeeds. PostgreSQL remains the sole source of truth.
* **No secrets in logs.** Only key *names* are logged, never values.
* **Namespaced keys.** Every key is prefixed with ``helpdesk:cache:`` so it can
  never collide with the rate-limit keys and can be cleared narrowly.
* **Versioned invalidation.** Cached analytics are stored under a *version*
  component; a mutation bumps the version, which logically invalidates every
  cached analytics payload in one ``INCR`` without scanning or deleting keys
  (never ``FLUSHDB``/``FLUSHALL``, never ``KEYS``).
* **Stampede mitigation.** A short, non-blocking rebuild lock means a burst of
  concurrent misses triggers one database load, not many. Losers serve the stale
  value when present, or compute normally if their lock attempt fails.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import uuid
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "helpdesk:cache"

# Cache identity for the admin support analytics aggregate. Bumping this version
# invalidates every cached analytics payload after any ticket/user mutation.
_ANALYTICS_KEY = f"{_KEY_PREFIX}:analytics:support"
_ANALYTICS_VERSION_KEY = f"{_KEY_PREFIX}:analytics:version"

# A short TTL bounds staleness even if an invalidation is missed. Mutations also
# bump the version immediately, so the TTL is a safety net, not the primary
# freshness mechanism. 60s is comfortably below how often a human reloads the
# dashboard while keeping the aggregate essentially "live".
_ANALYTICS_TTL_SECONDS = 60

# Best-effort rebuild lock; short so a crashed holder cannot block for long.
_REBUILD_LOCK_TTL_MS = 5_000

_redis_client: Redis | None = None


def _cache_configured() -> bool:
    return bool(settings.CACHE_ENABLED and settings.cache_redis_url)


async def get_cache_client() -> Redis | None:
    """Return the shared cache client, or ``None`` when caching is disabled.

    Connection failures are swallowed (returning ``None``) so caching can never
    break a request; callers simply proceed without a cache.
    """
    global _redis_client
    if not _cache_configured():
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        client = Redis.from_url(
            settings.cache_redis_url or "",
            decode_responses=True,
            socket_connect_timeout=settings.CACHE_REDIS_TIMEOUT_SECONDS,
            socket_timeout=settings.CACHE_REDIS_TIMEOUT_SECONDS,
        )
        await client.ping()
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning(
            "Cache disabled for now; Redis unavailable (%s)", type(exc).__name__
        )
        return None
    _redis_client = client
    return client


async def close_cache_client() -> None:
    global _redis_client
    client = _redis_client
    _redis_client = None
    if client is not None:
        await client.aclose()


async def _analytics_version(client: Redis) -> int:
    raw = await client.get(_ANALYTICS_VERSION_KEY)
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


async def get_analytics_cache() -> dict[str, Any] | None:
    """Return the cached analytics payload, or ``None`` on miss/disabled/error."""
    client = await get_cache_client()
    if client is None:
        return None
    try:
        version = await _analytics_version(client)
        raw = await client.get(f"{_ANALYTICS_KEY}:v{version}")
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning(
            "Analytics cache read failed (%s); using database", type(exc).__name__
        )
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        # A corrupt entry is treated as a miss and will be overwritten.
        return None


async def set_analytics_cache(payload: dict[str, Any]) -> None:
    """Store the analytics payload under the current version + TTL."""
    client = await get_cache_client()
    if client is None:
        return
    try:
        version = await _analytics_version(client)
        await client.set(
            f"{_ANALYTICS_KEY}:v{version}",
            json.dumps(payload),
            ex=_ANALYTICS_TTL_SECONDS,
        )
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Analytics cache write failed (%s)", type(exc).__name__)


async def invalidate_analytics_cache() -> None:
    """Logically invalidate all cached analytics (one ``INCR``, no key scan)."""
    client = await get_cache_client()
    if client is None:
        return
    try:
        await client.incr(_ANALYTICS_VERSION_KEY)
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning(
            "Analytics cache invalidation failed (%s); TTL will bound staleness",
            type(exc).__name__,
        )


async def try_acquire_rebuild_lock(token: str | None = None) -> str | None:
    """Try to take the analytics rebuild lock; return the token or ``None``.

    Uses ``SET NX PX`` so it is a single atomic, non-blocking call. Losing the
    race returns ``None`` (the caller serves stale data or computes directly).
    """
    client = await get_cache_client()
    if client is None:
        return None
    token = token or uuid.uuid4().hex
    try:
        acquired = await client.set(
            f"{_ANALYTICS_KEY}:lock", token, nx=True, px=_REBUILD_LOCK_TTL_MS
        )
    except (RedisError, OSError, TimeoutError):
        return None
    return token if acquired else None


async def release_rebuild_lock(token: str) -> None:
    client = await get_cache_client()
    if client is None:
        return
    with contextlib.suppress(RedisError, OSError, TimeoutError):
        # Only release a lock we still own (compare-and-delete).
        await client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            f"{_ANALYTICS_KEY}:lock",
            token,
        )


# Mutation paths whose success changes the analytics aggregate: ticket rows
# (status/priority/category/assignee/timestamps) and user rows (counts, roles,
# active status). Comments, attachments, feedback and messaging do NOT change it,
# so they are deliberately excluded to avoid needless invalidation.
_ANALYTICS_MUTATION_PATHS = (
    re.compile(r"^/api/v1/tickets/?$"),  # POST create
    re.compile(r"^/api/v1/tickets/[^/]+/?$"),  # PATCH update
    re.compile(r"^/api/v1/tickets/[^/]+/claim/?$"),
    re.compile(r"^/api/v1/tickets/[^/]+/assign/?$"),
    re.compile(r"^/api/v1/users/me/?$"),  # PATCH profile
    re.compile(r"^/api/v1/users/me/avatar/?$"),  # POST avatar
    re.compile(r"^/api/v1/users/[^/]+/?$"),  # PATCH user (admin)
    re.compile(r"^/api/v1/users/[^/]+/role/?$"),
    re.compile(r"^/api/v1/users/[^/]+/status/?$"),
)


class AnalyticsCacheInvalidationMiddleware:
    """Invalidate the analytics cache after a successful analytics-affecting write.

    Invalidation runs **after** the response is sent, so it adds no latency to
    the client and cannot alter the response. It is a single version ``INCR``
    (see :func:`invalidate_analytics_cache`) and is a no-op when caching is
    disabled or Redis is unavailable.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")
        relevant = (
            method in {"POST", "PUT", "PATCH", "DELETE"}
            and _cache_configured()
            and any(pattern.match(path) for pattern in _ANALYTICS_MUTATION_PATHS)
        )
        if not relevant:
            await self.app(scope, receive, send)
            return

        status_code = 0

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # Only a successful (2xx) write changed the data.
        if 200 <= status_code < 300:
            await invalidate_analytics_cache()
