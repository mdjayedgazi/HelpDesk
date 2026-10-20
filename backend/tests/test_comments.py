import pytest

from app.enums.enums import Role


@pytest.mark.asyncio
async def test_customer_adds_public_comment(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
        json={"body": "Any update?"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "Any update?"
    # Customers must not receive the internal flag.
    assert "is_internal" not in body


@pytest.mark.asyncio
async def test_customer_cannot_create_internal_note(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
        json={"body": "secret", "is_internal": True},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_internal_notes_hidden_from_customer(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    public = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": agent.username},
        json={"body": "We are looking into it."},
    )
    assert public.status_code == 201

    internal = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": agent.username},
        json={"body": "Customer is on the free plan.", "is_internal": True},
    )
    assert internal.status_code == 201
    assert internal.json()["is_internal"] is True

    customer_view = await client.get(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
    )
    bodies = [c["body"] for c in customer_view.json()]
    assert "We are looking into it." in bodies
    assert "Customer is on the free plan." not in bodies

    agent_view = await client.get(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": agent.username},
    )
    assert len(agent_view.json()) == 2


@pytest.mark.asyncio
async def test_customer_comment_list_omits_internal_field(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": agent.username},
        json={"body": "Public reply."},
    )

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
    )
    assert response.status_code == 200
    assert response.json()
    # The restricted property must be absent from every item, not just false.
    assert all("is_internal" not in comment for comment in response.json())


@pytest.mark.asyncio
async def test_cannot_comment_on_foreign_ticket(client, make_user, make_ticket):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": alice.username},
        json={"body": "Not mine"},
    )
    assert response.status_code == 404
