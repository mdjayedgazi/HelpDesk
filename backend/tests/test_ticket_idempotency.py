"""Idempotent ticket creation.

A repeated ``POST /api/v1/tickets`` with the same ``Idempotency-Key`` must
return the original ticket. Requests without a key keep the previous behavior
exactly.
"""

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory


def _payload() -> dict[str, str]:
    return {
        "title": "Cannot log in",
        "description": "The password is rejected every time.",
        "category": "ACCOUNT_ACCESS",
    }


async def _count(session_factory, model) -> int:
    async with session_factory() as session:
        return (await session.exec(select(func.count()).select_from(model))).one()


@pytest.mark.asyncio
async def test_repeated_key_returns_the_same_ticket(client, make_user, session_factory):
    customer = await make_user()
    headers = {"X-Test-User": customer.username, "Idempotency-Key": "retry-1"}

    first = await client.post("/api/v1/tickets", headers=headers, json=_payload())
    second = await client.post("/api/v1/tickets", headers=headers, json=_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    # The internal key is never exposed by the response schema.
    assert "client_request_id" not in first.json()
    assert await _count(session_factory, Ticket) == 1
    assert await _count(session_factory, TicketHistory) == 1


@pytest.mark.asyncio
async def test_different_keys_create_different_tickets(client, make_user):
    customer = await make_user()

    first = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username, "Idempotency-Key": "a"},
        json=_payload(),
    )
    second = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username, "Idempotency-Key": "b"},
        json=_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_no_key_preserves_existing_behavior(client, make_user):
    customer = await make_user()

    first = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json=_payload(),
    )
    second = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json=_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_blank_key_is_treated_as_absent(client, make_user):
    customer = await make_user()
    headers = {"X-Test-User": customer.username, "Idempotency-Key": "   "}

    first = await client.post("/api/v1/tickets", headers=headers, json=_payload())
    second = await client.post("/api/v1/tickets", headers=headers, json=_payload())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_invalid_key_is_rejected(client, make_user):
    customer = await make_user()

    response = await client.post(
        "/api/v1/tickets",
        headers={
            "X-Test-User": customer.username,
            "Idempotency-Key": "has spaces",
        },
        json=_payload(),
    )

    assert response.status_code == 422
    assert "Idempotency-Key" in response.json()["detail"]


@pytest.mark.asyncio
async def test_key_is_scoped_to_the_creator(client, make_user):
    first_customer = await make_user()
    second_customer = await make_user()
    key = "shared-key"

    first = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": first_customer.username, "Idempotency-Key": key},
        json=_payload(),
    )
    second = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": second_customer.username, "Idempotency-Key": key},
        json=_payload(),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_lost_race_returns_the_winning_ticket(
    client, make_user, session_factory, monkeypatch
):
    """Simulate two requests passing the pre-check before either commits.

    The in-memory SQLite test database uses one shared connection, so two
    requests cannot hold overlapping transactions. This test reproduces the
    exact production race deterministically instead: the second request's
    pre-check misses, its insert hits the partial unique index, and the handler
    must then return the row created by the winning request.
    """
    customer = await make_user()
    headers = {"X-Test-User": customer.username, "Idempotency-Key": "race"}

    first = await client.post("/api/v1/tickets", headers=headers, json=_payload())
    assert first.status_code == 201

    from app.api.routers import tickets as tickets_router

    real_lookup = tickets_router._find_idempotent_ticket
    calls = {"count": 0}

    async def precheck_misses_then_finds(session, creator_id, key):
        calls["count"] += 1
        if calls["count"] == 1:
            # This request does not see the other request's committed row yet.
            return None
        return await real_lookup(session, creator_id, key)

    monkeypatch.setattr(
        tickets_router, "_find_idempotent_ticket", precheck_misses_then_finds
    )

    second = await client.post("/api/v1/tickets", headers=headers, json=_payload())

    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert await _count(session_factory, Ticket) == 1


def test_idempotency_conflict_is_classified_narrowly():
    """Only the idempotency-key unique violation is treated as retryable."""
    from app.api.routers import tickets as tickets_router

    idempotency = IntegrityError(
        "INSERT INTO tickets ...",
        {},
        Exception(
            "UNIQUE constraint failed: tickets.created_by_user_id, "
            "tickets.client_request_id"
        ),
    )
    assert tickets_router._is_idempotency_conflict(idempotency) is True

    ticket_number = IntegrityError(
        "INSERT INTO tickets ...",
        {},
        Exception("UNIQUE constraint failed: tickets.ticket_number"),
    )
    assert tickets_router._is_idempotency_conflict(ticket_number) is False

    email = IntegrityError(
        "INSERT INTO users ...",
        {},
        Exception("UNIQUE constraint failed: users.email"),
    )
    assert tickets_router._is_idempotency_conflict(email) is False


@pytest.mark.asyncio
async def test_database_enforces_one_row_per_creator_and_key(
    session_factory, make_user
):
    customer = await make_user()
    common = {
        "title": "Duplicate",
        "description": "The database must reject the second row.",
        "created_by_user_id": customer.id,
        "client_request_id": "db-dup",
    }

    async with session_factory() as session:
        session.add(Ticket(ticket_number=9001, **common))
        await session.commit()

    async with session_factory() as session:
        session.add(Ticket(ticket_number=9002, **common))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_database_allows_many_null_keys(session_factory, make_user):
    """The partial unique index must not collide ordinary key-less rows."""
    customer = await make_user()

    async with session_factory() as session:
        session.add(
            Ticket(
                ticket_number=9101,
                title="One",
                description="No key.",
                created_by_user_id=customer.id,
            )
        )
        session.add(
            Ticket(
                ticket_number=9102,
                title="Two",
                description="Also no key.",
                created_by_user_id=customer.id,
            )
        )
        await session.commit()

    assert await _count(session_factory, Ticket) == 2
