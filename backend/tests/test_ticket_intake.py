"""Ticket intake requirements.

Covers the customer-facing intake form contract:

* ``title``, ``description`` and ``category`` are required; ``impact`` is the
  only urgency input a customer may give and the *server* maps it to the
  priority policy;
* the contact phone is optional, validated when present, normalized when
  blank, and never exposed by a public/customer response - only authorized
  staff can read it through the dedicated contact endpoint;
* the confirmation payload carries the ticket number, status, priority and
  category.
"""

import json

import pytest
from sqlmodel import select

from app.enums.enums import ImpactLevel, Role, TicketCategory, TicketPriority
from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory

INTAKE = "/api/v1/tickets"


async def _create(client, user, **overrides):
    payload = {
        "title": "Cannot log in",
        "description": "Password rejected after reset.",
        "category": "ACCOUNT_ACCESS",
    }
    payload.update(overrides)
    return await client.post(
        INTAKE, headers={"X-Test-User": user.username}, json=payload
    )


@pytest.mark.asyncio
async def test_category_is_required(client, make_user):
    customer = await make_user()
    response = await client.post(
        INTAKE,
        headers={"X-Test-User": customer.username},
        json={"title": "No category", "description": "Missing."},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_category_is_rejected(client, make_user):
    customer = await make_user()
    response = await _create(client, customer, category="NOT_A_CATEGORY")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_intake_response_carries_confirmation_fields(
    client, make_user, session_factory
):
    customer = await make_user()
    response = await _create(client, customer, category="BILLING", impact="HIGH")
    assert response.status_code == 201

    body = response.json()
    assert body["ticket_number"] >= 10001
    assert body["status"] == "OPEN"
    assert body["priority"] == "HIGH"
    assert body["category"] == "BILLING"
    assert body["created_by_user_id"] == str(customer.id)
    assert body["assignee_user_id"] is None

    async with session_factory() as session:
        stored = (await session.exec(select(Ticket))).one()
    assert stored.category == TicketCategory.BILLING
    assert stored.priority == TicketPriority.HIGH


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "impact,expected",
    [
        (None, "NORMAL"),
        ("LOW", "LOW"),
        ("MEDIUM", "NORMAL"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "URGENT"),
    ],
)
async def test_impact_maps_to_priority(client, make_user, impact, expected):
    customer = await make_user()
    response = await _create(client, customer, impact=impact)
    assert response.status_code == 201
    assert response.json()["priority"] == expected


@pytest.mark.asyncio
async def test_customer_cannot_set_priority_status_or_assignee(client, make_user):
    customer = await make_user()
    for protected in (
        {"priority": "URGENT"},
        {"status": "IN_PROGRESS"},
        {"assignee_user_id": None},
    ):
        response = await _create(client, customer, **protected)
        assert response.status_code == 422, protected


@pytest.mark.asyncio
async def test_customer_cannot_forge_owner_identity_or_route_to_staff(
    client, make_user, session_factory
):
    """The ticket owner is the authenticated user; nothing in the body can
    change that, name another customer, or pick an Agent/Admin/Owner."""
    customer = await make_user()
    victim = await make_user()
    agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    owner = await make_user(role=Role.OWNER)

    forged_bodies = [
        {"created_by_user_id": str(victim.id)},
        {"owner_id": str(victim.id)},
        {"user_id": str(victim.id)},
        {"email": victim.email},
        {"customer_email": victim.email},
        {"assignee_user_id": str(agent.id)},
        {"assignee_user_id": str(admin.id)},
        {"assignee_user_id": str(owner.id)},
        {"assignee_role": "owner"},
    ]
    for forged in forged_bodies:
        response = await _create(client, customer, **forged)
        assert response.status_code == 422, forged

    async with session_factory() as session:
        assert (await session.exec(select(Ticket))).all() == []

    # A clean request is always owned by the caller and auto-routed by the
    # backend (here to the only eligible agent), never by the body.
    response = await _create(client, customer)
    assert response.status_code == 201
    body = response.json()
    assert body["created_by_user_id"] == str(customer.id)
    assert body["assignee_user_id"] == str(agent.id)

    # The victim never sees the ticket.
    seen = await client.get(INTAKE, headers={"X-Test-User": victim.username})
    assert seen.status_code == 200 and seen.json() == []
    hidden = await client.get(
        f"{INTAKE}/{body['id']}", headers={"X-Test-User": victim.username}
    )
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_whitespace_only_title_and_description_rejected(client, make_user):
    customer = await make_user()
    blank_title = await _create(client, customer, title="   ")
    assert blank_title.status_code == 422

    blank_description = await _create(client, customer, description=" \t ")
    assert blank_description.status_code == 422


@pytest.mark.asyncio
async def test_phone_is_optional_and_normalized(client, make_user, session_factory):
    customer = await make_user()

    omitted = await _create(client, customer)
    assert omitted.status_code == 201

    blank = await _create(client, customer, contact_phone="   ")
    assert blank.status_code == 201

    provided = await _create(client, customer, contact_phone="  +1 555 010 9999  ")
    assert provided.status_code == 201

    async with session_factory() as session:
        tickets = (
            await session.exec(select(Ticket).order_by(Ticket.ticket_number))
        ).all()
    assert [t.contact_phone for t in tickets] == [
        None,
        None,
        "+1 555 010 9999",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phone",
    ["not-a-phone", "++15550109999", "1", "+1 (555) 010 9999 x12345678901234567890"],
)
async def test_invalid_phone_rejected(client, make_user, phone):
    customer = await make_user()
    response = await _create(client, customer, contact_phone=phone)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_phone_never_appears_in_customer_responses(
    client, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)
    # Store a phone directly so the check does not depend on intake.
    response = await client.patch(
        f"{INTAKE}/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"contact_phone": "+1 555 010 0001"},
    )
    assert response.status_code == 200
    assert "contact_phone" not in response.json()

    for url in (INTAKE, f"{INTAKE}/{ticket.id}"):
        listed = await client.get(url, headers={"X-Test-User": customer.username})
        assert listed.status_code == 200
        assert "contact_phone" not in json.dumps(listed.json())

    # Customers cannot reach the staff-only contact endpoint either.
    forbidden = await client.get(
        f"{INTAKE}/{ticket.id}/contact",
        headers={"X-Test-User": customer.username},
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_staff_contact_endpoint_matrix(client, make_user, make_ticket):
    assignee = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    owner = await make_user(role=Role.OWNER)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=assignee)

    # Seed the phone through the owning customer's update path.
    await client.patch(
        f"{INTAKE}/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"contact_phone": "+1 555 010 0002"},
    )

    allowed = await client.get(
        f"{INTAKE}/{ticket.id}/contact",
        headers={"X-Test-User": assignee.username},
    )
    assert allowed.status_code == 200
    assert allowed.json() == {
        "ticket_id": str(ticket.id),
        "contact_phone": "+1 555 010 0002",
    }

    for staff in (admin, owner):
        readable = await client.get(
            f"{INTAKE}/{ticket.id}/contact",
            headers={"X-Test-User": staff.username},
        )
        assert readable.status_code == 200
        assert readable.json()["contact_phone"] == "+1 555 010 0002"

    # An agent who does not work on the ticket cannot read its PII.
    denied = await client.get(
        f"{INTAKE}/{ticket.id}/contact",
        headers={"X-Test-User": other_agent.username},
    )
    assert denied.status_code == 404

    unauthenticated = await client.get(f"{INTAKE}/{ticket.id}/contact")
    assert unauthenticated.status_code == 401


@pytest.mark.asyncio
async def test_phone_can_be_cleared_and_history_keeps_no_value(
    client, make_user, make_ticket, session_factory
):
    customer = await make_user()
    ticket = await make_ticket(customer)

    number = "+1 555 010 0003"
    set_response = await client.patch(
        f"{INTAKE}/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"contact_phone": number},
    )
    assert set_response.status_code == 200

    clear_response = await client.patch(
        f"{INTAKE}/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"contact_phone": ""},
    )
    assert clear_response.status_code == 200

    async with session_factory() as session:
        stored = await session.get(Ticket, ticket.id)
        history = (
            await session.exec(
                select(TicketHistory).where(TicketHistory.ticket_id == ticket.id)
            )
        ).all()

    assert stored.contact_phone is None
    events = [h for h in history if h.event_type == "CONTACT_UPDATED"]
    assert len(events) == 2
    assert events[0].old_value == {"contact_phone_set": False}
    assert events[0].new_value == {"contact_phone_set": True}
    assert events[1].old_value == {"contact_phone_set": True}
    assert events[1].new_value == {"contact_phone_set": False}
    # No history row anywhere may contain the digits of the phone number.
    serialized = json.dumps([{"old": h.old_value, "new": h.new_value} for h in history])
    assert "555" not in serialized


@pytest.mark.asyncio
async def test_customer_cannot_touch_restricted_fields_on_update(
    client, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)

    for protected in (
        {"status": "CLOSED"},
        {"priority": "URGENT"},
        {"category": "OUTAGE"},
    ):
        response = await client.patch(
            f"{INTAKE}/{ticket.id}",
            headers={"X-Test-User": customer.username},
            json=protected,
        )
        assert response.status_code == 403, protected


@pytest.mark.asyncio
async def test_agent_can_recategorize_and_history_records_it(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"{INTAKE}/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"category": "BILLING"},
    )
    assert response.status_code == 200
    assert response.json()["category"] == "BILLING"

    async with session_factory() as session:
        events = (
            await session.exec(
                select(TicketHistory).where(
                    TicketHistory.ticket_id == ticket.id,
                    TicketHistory.event_type == "CATEGORY_CHANGED",
                )
            )
        ).all()
    assert len(events) == 1
    assert events[0].old_value == {"category": TicketCategory.OTHER.value}
    assert events[0].new_value == {"category": TicketCategory.BILLING.value}


@pytest.mark.asyncio
async def test_impact_values_are_validated(client, make_user):
    customer = await make_user()
    response = await _create(client, customer, impact="EXTREME")
    assert response.status_code == 422

    # The enum labels used by the API are the formal impact levels.
    assert {level.value for level in ImpactLevel} == {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }
