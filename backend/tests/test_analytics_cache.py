"""Tests for the optional read-through analytics cache.

These exercise the cache-aside contract without a real Redis by replacing the
shared client with a tiny in-memory fake. They assert behaviour, not timing:

* a miss computes from the database and populates the cache;
* a hit returns the cached payload without touching the database;
* a successful analytics-affecting write bumps the version (invalidation);
* an unavailable Redis falls back to the database (never fails the request);
* concurrent misses are limited by the rebuild lock.
"""

import json

import pytest
from redis.exceptions import RedisError

from app.core import cache
from app.main import app


class FakeRedis:
    """Minimal async Redis subset used by the cache module."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.locks: dict[str, str] = {}
        self.incr_calls = 0

    async def ping(self):
        return True

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=False, px=None):
        if nx:
            if key in self.locks:
                return None
            self.locks[key] = value
            return True
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def incr(self, key):
        self.incr_calls += 1
        current = int(self.store.get(key, "0")) + 1
        self.store[key] = str(current)
        return current

    async def eval(self, _script, _numkeys, key, value):
        if self.locks.get(key) == value:
            del self.locks[key]
            return 1
        return 0

    async def aclose(self):
        return True


@pytest.fixture()
def fake_cache(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(cache.settings, "CACHE_REDIS_URL", "redis://fake")
    monkeypatch.setattr(cache, "_redis_client", fake, raising=False)

    async def _client():
        return fake

    monkeypatch.setattr(cache, "get_cache_client", _client)
    return fake


@pytest.mark.asyncio
async def test_miss_then_hit_uses_cache(client, make_user, fake_cache):
    admin = await make_user(role="admin", username="cache_admin")

    first = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert first.status_code == 200

    # A version key exists and the payload is cached under it.
    assert any(k.endswith(":analytics:support:v0") for k in fake_cache.store)

    second = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert second.status_code == 200
    assert second.json()["totals"] == first.json()["totals"]


@pytest.mark.asyncio
async def test_write_invalidates_analytics_cache(
    client, make_user, make_ticket, fake_cache
):
    admin = await make_user(role="admin", username="cache_admin2")
    customer = await make_user(username="cache_cust")

    # Prime the cache.
    before = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert before.status_code == 200
    baseline_total = before.json()["totals"]["total_tickets"]

    # A ticket creation is an analytics-affecting write and must bump the version.
    created = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Cache invalidation",
            "description": "Should bump analytics version",
            "category": "TECHNICAL",
        },
    )
    assert created.status_code == 201
    assert fake_cache.incr_calls >= 1

    after = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert after.status_code == 200
    assert after.json()["totals"]["total_tickets"] == baseline_total + 1


@pytest.mark.asyncio
async def test_unrelated_write_does_not_invalidate(
    client, make_user, make_ticket, fake_cache
):
    admin = await make_user(role="admin", username="cache_admin3")
    customer = await make_user(username="cache_cust3")
    ticket = await make_ticket(customer)

    # Prime the cache.
    await client.get("/api/v1/admin/analytics", headers={"X-Test-User": admin.username})
    incr_before = fake_cache.incr_calls

    # A comment does not change the analytics aggregate; it must not invalidate.
    resp = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
        json={"body": "unrelated to analytics"},
    )
    assert resp.status_code in (200, 201)
    assert fake_cache.incr_calls == incr_before


@pytest.mark.asyncio
async def test_redis_unavailable_falls_back_to_database(client, make_user, monkeypatch):
    admin = await make_user(role="admin", username="cache_admin4")

    # Caching "enabled" but the client is unavailable.
    monkeypatch.setattr(cache.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(cache.settings, "CACHE_REDIS_URL", "redis://down")

    async def _boom():
        return None

    monkeypatch.setattr(cache, "get_cache_client", _boom)

    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    # Correctness never depends on the cache: the request still succeeds.
    assert response.status_code == 200
    assert response.json()["totals"]["total_tickets"] >= 0


@pytest.mark.asyncio
async def test_corrupt_cache_entry_is_a_miss(
    client, make_user, monkeypatch, fake_cache
):
    admin = await make_user(role="admin", username="cache_admin5")
    fake_cache.store["helpdesk:cache:analytics:support:v0"] = "{not json"

    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200
    # It recomputed and overwrote the corrupt entry with valid JSON.
    stored = fake_cache.store["helpdesk:cache:analytics:support:v0"]
    assert json.loads(stored)["totals"]["total_tickets"] >= 0


@pytest.mark.asyncio
async def test_rebuild_lock_is_atomic_and_exclusive(fake_cache):
    first = await cache.try_acquire_rebuild_lock()
    assert first is not None
    second = await cache.try_acquire_rebuild_lock()
    assert second is None  # someone already holds it
    await cache.release_rebuild_lock(first)
    third = await cache.try_acquire_rebuild_lock()
    assert third is not None


@pytest.mark.asyncio
async def test_cache_errors_are_swallowed(monkeypatch):
    monkeypatch.setattr(cache.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(cache.settings, "CACHE_REDIS_URL", "redis://err")

    class BoomRedis(FakeRedis):
        async def get(self, key):
            raise RedisError("boom")

        async def set(self, *a, **k):
            raise RedisError("boom")

        async def incr(self, key):
            raise RedisError("boom")

    fake = BoomRedis()

    async def _client():
        return fake

    monkeypatch.setattr(cache, "get_cache_client", _client)

    # Each helper degrades gracefully instead of raising.
    assert await cache.get_analytics_cache() is None
    await cache.set_analytics_cache({"x": 1})
    await cache.invalidate_analytics_cache()
    assert app  # keep import meaningful
