import pytest

from app.enums.enums import Role


@pytest.mark.asyncio
async def test_agent_reads_history_for_assigned_ticket(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"status": "IN_PROGRESS"},
    )

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": agent.username},
    )
    assert response.status_code == 200
    events = response.json()
    assert any(e["event_type"] == "STATUS_CHANGED" for e in events)
    status_event = next(e for e in events if e["event_type"] == "STATUS_CHANGED")
    assert status_event["new_value"] == {"status": "IN_PROGRESS"}


@pytest.mark.asyncio
async def test_admin_reads_history_for_any_ticket(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": admin.username},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_customer_cannot_read_own_ticket_history(client, make_user, make_ticket):
    """Customers must never reach the internal audit trail, even for their own
    ticket. The current status and public comments remain available elsewhere."""
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": customer.username},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_read_foreign_ticket_history(
    client, make_user, make_ticket
):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": alice.username},
    )
    # Role check runs first, so a customer is rejected before we reveal whether
    # the ticket exists.
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_cannot_read_foreign_ticket_history(client, make_user, make_ticket):
    """Agents still only see history for tickets they may view (404 hiding)."""
    agent = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=other_agent)

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": agent.username},
    )
    assert response.status_code == 404
