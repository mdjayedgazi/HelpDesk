import asyncio
import uuid

import pytest
from fastapi import Request
from sqlmodel import select

from app.core import rate_limit as rate_limit_module
from app.core.rate_limit import (
    RateLimitDecision,
    RateLimitUnavailable,
    RedisRateLimitStore,
    get_rate_limit_store,
    resolve_client_ip,
)
from app.main import app
from app.models.ticket import Ticket

TICKETS = "/api/v1/tickets"


class InMemoryRateLimitStore:
    """Deterministic test double for the shared store contract.

    This is a test helper only. Production has no in-memory fallback.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.counters: dict[tuple[str, int], int] = {}

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def hit(
        self, key: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        bucket = int(self.now // window_seconds)
        counter_key = (key, bucket)
        current = self.counters.get(counter_key, 0) + 1
        self.counters[counter_key] = current
        retry_after = max(window_seconds - int(self.now % window_seconds), 1)
        return RateLimitDecision(
            allowed=current <= limit,
            remaining=max(limit - current, 0),
            retry_after=retry_after,
        )


class FailingStore:
    async def hit(self, key, *, limit, window_seconds):
        raise RateLimitUnavailable("redis is down")


@pytest.fixture
def rate_limited(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_TICKET_CREATE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_COMMENT_CREATE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_ATTACHMENT_UPLOAD", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    store = InMemoryRateLimitStore()

    async def override_store():
        return store

    app.dependency_overrides[get_rate_limit_store] = override_store
    yield store
    app.dependency_overrides.pop(get_rate_limit_store, None)


def _ticket_payload() -> dict[str, str]:
    return {
        "title": "Rate limited ticket",
        "description": "Please help.",
        "category": "TECHNICAL",
    }


@pytest.mark.asyncio
async def test_ticket_creation_returns_429_with_retry_after(
    client, rate_limited, make_user
):
    customer = await make_user()

    first = await client.post(
        TICKETS,
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(),
    )
    second = await client.post(
        TICKETS,
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(),
    )
    third = await client.post(
        TICKETS,
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(),
    )

    assert first.status_code == 201
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.status_code == 201
    assert third.status_code == 429
    assert int(third.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_window_resets_after_retry_after(client, rate_limited, make_user):
    customer = await make_user()
    for _ in range(2):
        response = await client.post(
            TICKETS,
            headers={"X-Test-User": customer.username},
            json=_ticket_payload(),
        )
        assert response.status_code == 201

    limited = await client.post(
        TICKETS,
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(),
    )
    assert limited.status_code == 429

    rate_limited.advance(61)
    recovered = await client.post(
        TICKETS,
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(),
    )
    assert recovered.status_code == 201


@pytest.mark.asyncio
async def test_comment_endpoint_is_covered(
    client, rate_limited, make_user, make_ticket, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_COMMENT_CREATE", 1)
    customer = await make_user()
    ticket = await make_ticket(customer)
    path = f"/api/v1/tickets/{ticket.id}/comments"

    first = await client.post(
        path,
        headers={"X-Test-User": customer.username},
        json={"body": "First"},
    )
    second = await client.post(
        path,
        headers={"X-Test-User": customer.username},
        json={"body": "Second"},
    )

    assert first.status_code == 201
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_upload_endpoint_is_covered(
    client, rate_limited, make_user, make_ticket, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ATTACHMENT_UPLOAD", 1)
    customer = await make_user()
    ticket = await make_ticket(customer)
    path = f"/api/v1/tickets/{ticket.id}/attachments"

    first = await client.post(
        path,
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"first", "text/plain")},
    )
    second = await client.post(
        path,
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"second", "text/plain")},
    )

    assert first.status_code == 201
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_limiter_is_per_user(client, rate_limited, make_user):
    alice = await make_user()
    bob = await make_user()

    for _ in range(2):
        response = await client.post(
            TICKETS,
            headers={"X-Test-User": alice.username},
            json=_ticket_payload(),
        )
        assert response.status_code == 201

    alice_limited = await client.post(
        TICKETS,
        headers={"X-Test-User": alice.username},
        json=_ticket_payload(),
    )
    bob_allowed = await client.post(
        TICKETS,
        headers={"X-Test-User": bob.username},
        json=_ticket_payload(),
    )

    assert alice_limited.status_code == 429
    assert bob_allowed.status_code == 201


@pytest.mark.asyncio
async def test_unavailable_store_fails_closed(
    client, rate_limited, make_user, session_factory
):
    async def failing_store():
        return FailingStore()

    app.dependency_overrides[get_rate_limit_store] = failing_store
    customer = await make_user()

    response = await client.post(
        TICKETS,
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(),
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    async with session_factory() as session:
        tickets = (await session.exec(select(Ticket))).all()
    assert tickets == []


@pytest.mark.asyncio
async def test_get_store_returns_none_when_disabled(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    assert await get_rate_limit_store() is None


def _request(client_host: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": headers,
            "client": (client_host, 12345),
        }
    )


def test_forwarded_header_is_ignored_without_trusted_proxies(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXIES", [])
    request = _request("203.0.113.9", "198.51.100.7")

    assert resolve_client_ip(request) == "203.0.113.9"


def test_forwarded_header_uses_rightmost_untrusted_hop(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXIES", ["10.0.0.0/8"])
    request = _request(
        "10.1.2.3",
        "1.2.3.4, 198.51.100.7, 10.0.0.5",
    )

    assert resolve_client_ip(request) == "198.51.100.7"


def test_invalid_forwarded_hop_falls_back_to_peer(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXIES", ["10.0.0.0/8"])
    request = _request("10.1.2.3", "not-an-ip")

    assert resolve_client_ip(request) == "10.1.2.3"


class BrokenRedis:
    async def eval(self, *args, **kwargs):
        raise ConnectionError("connection refused")


@pytest.mark.asyncio
async def test_redis_store_converts_connection_errors():
    store = RedisRateLimitStore(BrokenRedis())  # type: ignore[arg-type]

    with pytest.raises(RateLimitUnavailable):
        await store.hit("key", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_unknown_policy_name_is_rejected():
    with pytest.raises(ValueError, match="Unknown rate-limit policy"):
        rate_limit_module._policy_for("not-a-policy")


@pytest.mark.asyncio
async def test_redis_backend_against_disposable_redis():
    """Optional integration test; CI provides HD_TEST_REDIS_URL."""
    import os

    from redis.asyncio import Redis

    url = os.getenv("HD_TEST_REDIS_URL")
    if not url:
        pytest.skip("HD_TEST_REDIS_URL is not set")

    client = Redis.from_url(url, decode_responses=False)
    key = f"helpdesk:test:{uuid.uuid4().hex}"
    try:
        store = RedisRateLimitStore(client)
        first = await store.hit(key, limit=2, window_seconds=1)
        second = await store.hit(key, limit=2, window_seconds=1)
        third = await store.hit(key, limit=2, window_seconds=1)

        assert first.allowed is True
        assert second.allowed is True
        assert third.allowed is False
        assert third.retry_after >= 1

        await asyncio.sleep(1.1)
        recovered = await store.hit(key, limit=2, window_seconds=1)
        assert recovered.allowed is True
    finally:
        await client.delete(key)
        await client.aclose()
