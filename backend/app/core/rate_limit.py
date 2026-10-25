"""Redis-backed, per-user rate limiting for abuse-prone write endpoints.

Design
------
* The limiter is **disabled by default**. Enabling it requires an explicit
  ``RATE_LIMIT_REDIS_URL``; there is no in-process fallback that would pretend
  to protect multiple workers.
* Keys are scoped to the authenticated user (or the resolved client IP only
  when a caller has no user), so a user cannot bypass a limit by changing
  ``X-Forwarded-For``.
* A fixed window is implemented atomically in Redis. The first request in a
  window sets the TTL; later requests read the remaining TTL for
  ``Retry-After``.
* If Redis is unavailable or times out, protected endpoints return ``503``
  rather than allowing the request. This is deliberately fail-closed.
* ``X-Forwarded-For`` is trusted only when the direct peer is in
  ``RATE_LIMIT_TRUSTED_PROXIES``. Without that configuration the header is
  ignored.

The limiter protects selected write endpoints, not every read. That keeps
normal dashboard polling and ticket viewing outside the write budget.
"""

import asyncio
import ipaddress
import logging
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.auth import user_dependency
from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "helpdesk:rate"

# Atomic fixed-window counter. ``EXPIRE`` is only set when the key is first
# created; a missing TTL is repaired defensively. Returns [count, ttl].
_INCR_WITH_TTL = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    ttl = tonumber(ARGV[2])
end
return {current, ttl}
"""


class RateLimitUnavailable(RuntimeError):
    """The shared limiter cannot be reached or returned an unusable result."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: int


class RateLimitStore(Protocol):
    async def hit(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Consume one unit from ``key`` and return the decision."""
        ...


class UnavailableRateLimitStore:
    """Sentinel used when rate limiting is enabled but Redis is not configured.

    It is intentionally not a permissive fallback: calling ``hit`` raises, and
    the dependency converts that into ``503``.
    """

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def hit(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        raise RateLimitUnavailable(self._reason)


class RedisRateLimitStore:
    """Fixed-window counter backed by a shared Redis instance."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def hit(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        try:
            result = await self._client.eval(
                _INCR_WITH_TTL,
                1,
                key,
                limit,
                window_seconds,
            )
        except (RedisError, OSError, TimeoutError) as exc:
            raise RateLimitUnavailable("Redis rate-limit request failed") from exc

        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise RateLimitUnavailable("Redis rate-limit response was malformed")

        try:
            current = int(result[0])
            ttl = int(result[1])
        except (TypeError, ValueError) as exc:
            raise RateLimitUnavailable(
                "Redis rate-limit response was not numeric"
            ) from exc

        return RateLimitDecision(
            allowed=current <= limit,
            remaining=max(limit - current, 0),
            retry_after=max(ttl, 1),
        )


_redis_client: Redis | None = None
_redis_lock = asyncio.Lock()


async def _get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    if not settings.RATE_LIMIT_REDIS_URL:
        raise RateLimitUnavailable("RATE_LIMIT_REDIS_URL is not configured")

    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client

        client = Redis.from_url(
            settings.RATE_LIMIT_REDIS_URL,
            decode_responses=False,
            socket_connect_timeout=settings.RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
            socket_timeout=settings.RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        )
        try:
            await client.ping()
        except (RedisError, OSError, TimeoutError) as exc:
            await client.aclose()
            raise RateLimitUnavailable("Redis rate-limit ping failed") from exc

        _redis_client = client
        return client


async def get_rate_limit_store() -> RateLimitStore | None:
    """Return the shared store, or ``None`` when rate limiting is disabled.

    A missing URL or an unreachable Redis produces an ``UnavailableRateLimitStore``
    so the protected endpoint can fail closed with a clear 503.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return None

    if not settings.RATE_LIMIT_REDIS_URL:
        return UnavailableRateLimitStore("RATE_LIMIT_REDIS_URL is not configured")

    try:
        client = await _get_redis_client()
    except RateLimitUnavailable as exc:
        return UnavailableRateLimitStore(str(exc))

    return RedisRateLimitStore(client)


RateLimitStoreDependency = Annotated[
    RateLimitStore | None,
    Depends(get_rate_limit_store),
]


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


def _policy_for(name: str) -> RateLimitPolicy:
    """Read the current settings so tests and operators can tune limits.

    Unknown names are a programming error and fail at import/startup rather
    than silently disabling protection.
    """
    policies = {
        "ticket_create": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_TICKET_CREATE,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        "comment_create": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_COMMENT_CREATE,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        "attachment_upload": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_ATTACHMENT_UPLOAD,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        "feedback_create": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_FEEDBACK_CREATE,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        "account_request_create": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_ACCOUNT_REQUEST_CREATE,
            settings.RATE_LIMIT_ACCOUNT_REQUEST_WINDOW_SECONDS,
        ),
        "account_request_comment": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_ACCOUNT_REQUEST_COMMENT,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        "staff_message_create": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_STAFF_MESSAGE_CREATE,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        "internal_message_create": RateLimitPolicy(
            name,
            settings.RATE_LIMIT_INTERNAL_MESSAGE_CREATE,
            settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
    }
    try:
        return policies[name]
    except KeyError as exc:
        raise ValueError(f"Unknown rate-limit policy: {name}") from exc


def _trusted_proxy_networks() -> tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network, ...
]:
    return tuple(
        ipaddress.ip_network(value, strict=False)
        for value in settings.RATE_LIMIT_TRUSTED_PROXIES
    )


def _is_trusted_proxy(
    host: str,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in networks)


def resolve_client_ip(request: Request) -> str:
    """Resolve the caller IP without trusting spoofable headers by default.

    ``X-Forwarded-For`` is used only when the direct peer is explicitly listed
    as a trusted proxy. The chain is walked from the right, skipping trusted
    proxies, so a client-supplied leftmost value cannot spoof the source.
    Invalid hops fall back to the direct peer.
    """
    peer = request.client.host if request.client else "unknown"
    networks = _trusted_proxy_networks()
    if not networks or not _is_trusted_proxy(peer, networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if not hops:
        return peer

    for hop in reversed(hops):
        if not _is_trusted_proxy(hop, networks):
            try:
                ipaddress.ip_address(hop)
            except ValueError:
                return peer
            return hop
    return peer


def rate_limit(policy_name: str):
    """Create a FastAPI dependency that enforces one named policy."""

    async def dependency(
        request: Request,
        response: Response,
        user: user_dependency,
        store: RateLimitStoreDependency,
    ) -> None:
        policy = _policy_for(policy_name)
        if store is None:
            return

        # Authenticated writes are scoped by user id; the IP fallback exists for
        # completeness and never lets a user evade a limit by changing headers.
        scope = (
            f"user:{user.id}"
            if user is not None
            else f"ip:{resolve_client_ip(request)}"
        )
        key = f"{_KEY_PREFIX}:{policy.name}:{scope}"

        try:
            decision = await store.hit(
                key,
                limit=policy.limit,
                window_seconds=policy.window_seconds,
            )
        except RateLimitUnavailable as exc:
            logger.error(
                "Rate limiter unavailable for policy %s: %s",
                policy.name,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Rate limiting is temporarily unavailable; try again later",
                headers={"Retry-After": "5"},
            ) from None

        response.headers["X-RateLimit-Limit"] = str(policy.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Reset"] = str(decision.retry_after)

        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests; slow down and try again",
                headers={"Retry-After": str(decision.retry_after)},
            )

    return dependency
