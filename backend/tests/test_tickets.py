import uuid

import pytest

from app.enums.enums import Role, TicketStatus


@pytest.mark.asyncio
async def test_customer_creates_ticket_owned_by_self(client, make_user):
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
    body = response.json()
    assert body["created_by_user_id"] == str(customer.id)
    assert body["status"] == "OPEN"
    assert body["priority"] == "NORMAL"
    assert body["ticket_number"] >= 10001


@pytest.mark.asyncio
async def test_customer_cannot_set_owner_or_priority(client, make_user):
    customer = await make_user()
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Sneaky",
            "description": "Trying to set protected fields.",
            "category": "TECHNICAL",
            "created_by_user_id": str(uuid.uuid4()),
            "priority": "URGENT",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_customer_only_lists_own_tickets(client, make_user, make_ticket):
    alice = await make_user()
    bob = await make_user()
    await make_ticket(alice, title="Alice ticket")
    await make_ticket(bob, title="Bob ticket")

    response = await client.get(
        "/api/v1/tickets", headers={"X-Test-User": alice.username}
    )
    assert response.status_code == 200
    titles = [t["title"] for t in response.json()]
    assert titles == ["Alice ticket"]


@pytest.mark.asyncio
async def test_customer_cannot_read_other_ticket(client, make_user, make_ticket):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": alice.username},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_customer_cannot_change_status(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"status": "CLOSED"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_customer_can_edit_title_while_open(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"title": "Updated title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"


@pytest.mark.asyncio
async def test_customer_cannot_edit_resolved_ticket(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer, status=TicketStatus.RESOLVED)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"title": "Too late"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_invalid_ticket_id_returns_422(client, make_user):
    customer = await make_user()
    response = await client.get(
        "/api/v1/tickets/not-a-uuid",
        headers={"X-Test-User": customer.username},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_sees_queue_and_own_assigned(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    customer = await make_user()

    unassigned = await make_ticket(customer, title="Queue ticket")
    mine = await make_ticket(customer, title="Mine", assignee=agent)
    theirs = await make_ticket(customer, title="Theirs", assignee=other_agent)

    response = await client.get(
        "/api/v1/tickets", headers={"X-Test-User": agent.username}
    )
    assert response.status_code == 200
    ids = {t["id"] for t in response.json()}
    assert str(unassigned.id) in ids
    assert str(mine.id) in ids
    assert str(theirs.id) not in ids


@pytest.mark.asyncio
async def test_agent_can_claim_unassigned_ticket(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/claim",
        headers={"X-Test-User": agent.username},
    )
    assert response.status_code == 200
    assert response.json()["assignee_user_id"] == str(agent.id)


@pytest.mark.asyncio
async def test_agent_cannot_assign_ticket(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    target = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": agent.username},
        json={"assignee_user_id": str(target.id)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_assigns_ticket_and_notifies_agent(
    client, make_user, make_ticket, session_factory
):
    from sqlmodel import select

    from app.enums.enums import NotificationType
    from app.models.notification import Notification

    admin = await make_user(role=Role.ADMIN)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": str(agent.id)},
    )
    assert response.status_code == 200
    assert response.json()["assignee_user_id"] == str(agent.id)

    async with session_factory() as session:
        result = await session.exec(
            select(Notification).where(
                Notification.recipient_user_id == agent.id,
                Notification.type == NotificationType.TICKET_ASSIGNED,
            )
        )
        assert result.first() is not None


@pytest.mark.asyncio
async def test_agent_invalid_status_transition_rejected(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    # OPEN -> RESOLVED is not an allowed transition.
    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"status": "RESOLVED"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_admin_cannot_use_agent_queue_endpoints(client, make_user, make_ticket):
    """The agent queue is agent-only; admins manage tickets elsewhere."""
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    assigned = await client.get(
        "/api/v1/tickets/assigned", headers={"X-Test-User": admin.username}
    )
    assert assigned.status_code == 403

    claim = await client.post(
        f"/api/v1/tickets/{ticket.id}/claim",
        headers={"X-Test-User": admin.username},
    )
    assert claim.status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_claim_ticket(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/claim",
        headers={"X-Test-User": customer.username},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_valid_transition_and_customer_notified(
    client, make_user, make_ticket, session_factory
):
    from sqlmodel import select

    from app.enums.enums import NotificationType
    from app.models.notification import Notification

    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"status": "IN_PROGRESS"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"

    async with session_factory() as session:
        result = await session.exec(
            select(Notification).where(
                Notification.recipient_user_id == customer.id,
                Notification.type == NotificationType.STATUS_CHANGED,
            )
        )
        assert result.first() is not None
