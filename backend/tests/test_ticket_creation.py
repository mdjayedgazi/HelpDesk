"""Regression tests for ticket creation (D1) and its customer-only policy.

These tests monkeypatch ``next_ticket_number`` in the *router* module so we can
force a ticket-number collision without racing real requests.
"""

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.api.routers import tickets as tickets_router
from app.enums.enums import Role
from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory


async def _count(session_factory, model) -> int:
    async with session_factory() as session:
        return (await session.exec(select(func.count()).select_from(model))).one()


def test_ticket_number_is_required_by_model_and_schema():
    """F-10: the invariant is enforced at the model and database layer."""
    field = Ticket.model_fields["ticket_number"]
    assert field.is_required()
    assert Ticket.__table__.c.ticket_number.nullable is False


@pytest.mark.asyncio
async def test_normal_creation_writes_a_single_ticket_and_history(
    client, make_user, session_factory
):
    customer = await make_user()
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Cannot log in",
            "description": "Password rejected.",
            "category": "ACCOUNT_ACCESS",
        },
    )
    assert response.status_code == 201

    assert await _count(session_factory, Ticket) == 1
    assert await _count(session_factory, TicketHistory) == 1


@pytest.mark.asyncio
async def test_ticket_number_collision_then_success(
    client, make_user, make_ticket, monkeypatch, session_factory
):
    customer = await make_user()
    existing = await make_ticket(customer)

    # First attempt collides with the existing number, second succeeds.
    numbers = iter([existing.ticket_number, existing.ticket_number + 1])

    async def fake_next_ticket_number(session):
        return next(numbers)

    monkeypatch.setattr(tickets_router, "next_ticket_number", fake_next_ticket_number)

    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Retry me",
            "description": "Collides once.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 201
    assert response.json()["ticket_number"] == existing.ticket_number + 1

    # Exactly the pre-existing ticket plus the new one. The rolled-back
    # attempt left no extra history row behind: only the new ticket records
    # its creation (the fixture-created ticket writes no history).
    assert await _count(session_factory, Ticket) == 2
    assert await _count(session_factory, TicketHistory) == 1


@pytest.mark.asyncio
async def test_ticket_number_retry_exhaustion_returns_conflict(
    client, make_user, make_ticket, monkeypatch, session_factory
):
    customer = await make_user()
    existing = await make_ticket(customer)

    attempts = {"count": 0}

    async def always_collide(session):
        attempts["count"] += 1
        return existing.ticket_number

    monkeypatch.setattr(tickets_router, "next_ticket_number", always_collide)

    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Never succeeds",
            "description": "Always collides.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 409
    assert attempts["count"] == tickets_router._TICKET_NUMBER_RETRIES

    # No partial ticket or history row is left behind.
    assert await _count(session_factory, Ticket) == 1
    assert await _count(session_factory, TicketHistory) == 0


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_not_retried(
    client, make_user, monkeypatch, session_factory
):
    customer = await make_user()

    attempts = {"count": 0}

    async def fake_next_ticket_number(session):
        attempts["count"] += 1
        return 10001

    original_record_history = tickets_router.record_history

    def boom(*args, **kwargs):
        raise IntegrityError("INSERT", {}, Exception("some other constraint"))

    monkeypatch.setattr(tickets_router, "next_ticket_number", fake_next_ticket_number)
    monkeypatch.setattr(tickets_router, "record_history", boom)

    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Bad constraint",
            "description": "Unrelated failure.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 409
    # The retry loop must not treat this as a ticket-number collision.
    assert attempts["count"] == 1
    assert await _count(session_factory, Ticket) == 0

    # The session/transaction recovered cleanly: the next request works.
    monkeypatch.setattr(tickets_router, "record_history", original_record_history)
    recovered = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Now fine",
            "description": "Recovered.",
            "category": "TECHNICAL",
        },
    )
    assert recovered.status_code == 201
    assert await _count(session_factory, Ticket) == 1


@pytest.mark.asyncio
async def test_agent_cannot_create_ticket(client, make_user):
    agent = await make_user(role=Role.AGENT)
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": agent.username},
        json={
            "title": "Staff ticket",
            "description": "Should be rejected.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_create_ticket(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": admin.username},
        json={
            "title": "Staff ticket",
            "description": "Should be rejected.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 403
