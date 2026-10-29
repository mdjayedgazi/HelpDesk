"""Private staff <-> Owner messaging.

The authorization rules are enforced in the backend, not just hidden in the UI:

* CUSTOMERs cannot read, start, send, or mark read - every endpoint answers
  ``403`` from the role dependency;
* an AGENT/ADMIN only ever sees their own conversation; another agent's thread
  is ``404`` (not ``403``) so its existence is not revealed;
* the OWNER sees the whole inbox and replies inside each thread;
* recipients are always derived from the conversation, never from the request.
"""

import uuid
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlmodel import func, select

from app.enums.enums import NotificationType, Role
from app.models.notification import Notification
from app.models.staff_message import StaffConversation, StaffMessage

BASE = "/api/v1/staff-messages/conversations"


async def _start(client, user, subject=None):
    payload = {} if subject is None else {"subject": subject}
    return await client.post(BASE, headers={"X-Test-User": user.username}, json=payload)


async def _send(client, user, conversation_id, body):
    return await client.post(
        f"{BASE}/{conversation_id}/messages",
        headers={"X-Test-User": user.username},
        json={"body": body},
    )


@pytest.mark.asyncio
async def test_customer_is_denied_everywhere(client, make_user):
    customer = await make_user()
    await make_user(role=Role.OWNER)

    # Build a real conversation as an agent so the customer denial can also be
    # checked against an existing conversation id.
    agent = await make_user(role=Role.AGENT)
    started = await _start(client, agent)
    assert started.status_code == 200
    conversation_id = started.json()["id"]

    headers = {"X-Test-User": customer.username}
    assert (await client.get(BASE, headers=headers)).status_code == 403
    assert (await _start(client, customer)).status_code == 403
    assert (
        await client.get(f"{BASE}/{conversation_id}", headers=headers)
    ).status_code == 403
    assert (await _send(client, customer, conversation_id, "hello?")).status_code == 403
    assert (
        await client.post(f"{BASE}/{conversation_id}/read", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_agent_starts_one_conversation_with_the_owner(client, make_user):
    owner = await make_user(role=Role.OWNER, username="the_owner")
    agent = await make_user(role=Role.AGENT, username="agent_smith")

    first = await _start(client, agent, subject="Need guidance")
    assert first.status_code == 200
    body = first.json()
    assert body["subject"] == "Need guidance"
    assert body["owner_user_id"] == str(owner.id)
    assert body["staff_user_id"] == str(agent.id)
    assert body["staff_full_name"] == agent.full_name
    assert body["message_count"] == 0
    assert body["unread_count"] == 0

    # Idempotent: one thread per staff member.
    second = await _start(client, agent, subject="Another subject")
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]
    assert second.json()["subject"] == "Need guidance"


@pytest.mark.asyncio
async def test_owner_cannot_start_a_conversation(client, make_user):
    owner = await make_user(role=Role.OWNER)
    response = await _start(client, owner)
    assert response.status_code == 403
    assert "agents and admins" in response.json()["detail"]

    # The list endpoint still works for the Owner (the inbox starts empty).
    inbox = await client.get(BASE, headers={"X-Test-User": owner.username})
    assert inbox.status_code == 200
    assert inbox.json() == []


@pytest.mark.asyncio
async def test_customer_cannot_read_other_agents_threads(client, make_user):
    """Agent isolation matrix: list/detail/reply/read are participant-scoped."""
    await make_user(role=Role.OWNER)
    alice = await make_user(role=Role.AGENT, username="alice_agent")
    bob = await make_user(role=Role.AGENT, username="bob_agent")

    alice_conversation = (await _start(client, alice)).json()["id"]
    bob_conversation = (await _start(client, bob)).json()["id"]
    assert alice_conversation != bob_conversation

    bob_headers = {"X-Test-User": bob.username}
    listed = await client.get(BASE, headers=bob_headers)
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [bob_conversation]

    assert (
        await client.get(f"{BASE}/{alice_conversation}", headers=bob_headers)
    ).status_code == 404
    assert (
        await _send(client, bob, alice_conversation, "reading your mail")
    ).status_code == 404
    assert (
        await client.post(f"{BASE}/{alice_conversation}/read", headers=bob_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_message_flow_notifications_and_read_tracking(
    client, make_user, session_factory
):
    owner = await make_user(role=Role.OWNER, username="owner_inbox")
    agent = await make_user(role=Role.AGENT, username="agent_messaging")

    conversation_id = (await _start(client, agent, subject="Escalation")).json()["id"]

    sent = await _send(client, agent, conversation_id, "Can you review ticket #10042?")
    assert sent.status_code == 201
    message = sent.json()
    assert message["sender_user_id"] == str(agent.id)
    assert message["read_at"] is None

    # The Owner is notified, without leaking the message body.
    async with session_factory() as session:
        notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == owner.id,
                    Notification.type == NotificationType.STAFF_MESSAGE_RECEIVED,
                )
            )
        ).all()
    assert len(notifications) == 1
    assert notifications[0].related_conversation_id is not None
    assert str(notifications[0].related_conversation_id) == conversation_id
    assert "10042" not in notifications[0].message

    # Owner inbox: one unread message addressed to the Owner.
    owner_headers = {"X-Test-User": owner.username}
    inbox = await client.get(BASE, headers=owner_headers)
    assert inbox.status_code == 200
    assert len(inbox.json()) == 1
    assert inbox.json()[0]["unread_count"] == 1

    # Owner replies.
    reply = await _send(client, owner, conversation_id, "Reviewing it now.")
    assert reply.status_code == 201

    async with session_factory() as session:
        reply_notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == agent.id,
                    Notification.type == NotificationType.OWNER_MESSAGE_RECEIVED,
                )
            )
        ).all()
    assert len(reply_notifications) == 1

    # The agent now has one unread message (the Owner's reply); their own
    # message is never "unread" for them.
    agent_headers = {"X-Test-User": agent.username}
    agent_inbox = await client.get(BASE, headers=agent_headers)
    assert agent_inbox.json()[0]["unread_count"] == 1
    assert agent_inbox.json()[0]["message_count"] == 2
    assert agent_inbox.json()[0]["last_message_preview"] == "Reviewing it now."

    detail = await client.get(f"{BASE}/{conversation_id}", headers=agent_headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2

    read = await client.post(f"{BASE}/{conversation_id}/read", headers=agent_headers)
    assert read.status_code == 200
    assert read.json() == {"updated": 1}

    after = await client.get(BASE, headers=agent_headers)
    assert after.json()[0]["unread_count"] == 0

    async with session_factory() as session:
        rows = (
            await session.exec(
                select(StaffMessage)
                .where(StaffMessage.conversation_id == UUID(conversation_id))
                .order_by(StaffMessage.created_at.asc())
            )
        ).all()
    by_sender = {m.sender_user_id: m for m in rows}
    # The Owner's reply to the agent is marked read; the agent's own message
    # still belongs to the Owner's unread set.
    assert by_sender[owner.id].read_at is not None
    assert by_sender[agent.id].read_at is None


@pytest.mark.asyncio
async def test_owner_inbox_covers_every_staff_thread(client, make_user):
    owner = await make_user(role=Role.OWNER, username="owner_big_inbox")
    agent = await make_user(role=Role.AGENT, username="inbox_agent")
    admin = await make_user(role=Role.ADMIN, username="inbox_admin")

    agent_thread = (await _start(client, agent)).json()["id"]
    admin_thread = (await _start(client, admin)).json()["id"]

    owner_inbox = await client.get(BASE, headers={"X-Test-User": owner.username})
    assert owner_inbox.status_code == 200
    ids = {c["id"] for c in owner_inbox.json()}
    assert ids == {agent_thread, admin_thread}

    # An agent still only sees their own thread.
    agent_inbox = await client.get(BASE, headers={"X-Test-User": agent.username})
    assert {c["id"] for c in agent_inbox.json()} == {agent_thread}


@pytest.mark.asyncio
async def test_owner_inbox_is_paginated(client, make_user):
    owner = await make_user(role=Role.OWNER, username="owner_paginated")
    agents = [
        await make_user(role=Role.AGENT, username=f"page_agent_{index}")
        for index in range(3)
    ]
    for agent in agents:
        assert (await _start(client, agent)).status_code == 200

    headers = {"X-Test-User": owner.username}
    first_page = await client.get(f"{BASE}?limit=2", headers=headers)
    second_page = await client.get(f"{BASE}?limit=2&offset=2", headers=headers)

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 1
    assert {c["id"] for c in first_page.json()}.isdisjoint(
        {c["id"] for c in second_page.json()}
    )


@pytest.mark.asyncio
async def test_owner_inbox_summaries_do_not_issue_n_plus_one_queries(
    client, make_user, session_factory
):
    owner = await make_user(role=Role.OWNER, username="owner_query_count")
    for index in range(4):
        agent = await make_user(role=Role.AGENT, username=f"query_agent_{index}")
        conversation_id = (await _start(client, agent)).json()["id"]
        assert (
            await _send(client, agent, conversation_id, f"message {index}")
        ).status_code == 201

    engine = session_factory.kw["bind"].sync_engine
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = await client.get(BASE, headers={"X-Test-User": owner.username})
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200
    assert len(response.json()) == 4
    # conversations + aggregates + two latest-message windows + participants
    assert len(statements) <= 6, "\n\n".join(statements)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    ["", "   ", "\n\t ", "x" * 5001],
)
async def test_invalid_message_bodies_rejected(client, make_user, body):
    await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    conversation_id = (await _start(client, agent)).json()["id"]

    response = await _send(client, agent, conversation_id, body)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_message_body_is_trimmed(client, make_user):
    await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    conversation_id = (await _start(client, agent)).json()["id"]

    response = await _send(client, agent, conversation_id, "  padded  ")
    assert response.status_code == 201
    assert response.json()["body"] == "padded"


@pytest.mark.asyncio
async def test_no_owner_configured_is_a_clear_conflict(client, make_user):
    agent = await make_user(role=Role.AGENT)
    response = await _start(client, agent)
    assert response.status_code == 409
    assert "Owner" in response.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_thread_creation_is_impossible(
    client, make_user, session_factory
):
    await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)

    first = await _start(client, agent)
    second = await _start(client, agent)
    assert first.json()["id"] == second.json()["id"]

    async with session_factory() as session:
        count = (
            await session.exec(select(func.count()).select_from(StaffConversation))
        ).one()
    assert count == 1


@pytest.mark.asyncio
async def test_unknown_conversation_is_not_found(client, make_user):
    import uuid

    await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)

    response = await client.get(
        f"{BASE}/{uuid.uuid4()}", headers={"X-Test-User": agent.username}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_spoofed_sender_and_recipient_ids_are_rejected(
    client, make_user, session_factory
):
    """The sender is the authenticated user; the recipient comes from the thread.

    Both schemas forbid unknown fields, so a client cannot even *attempt* to
    speak as somebody else or redirect a message: the request is rejected with
    ``422`` and nothing is stored.
    """
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    conversation_id = (await _start(client, agent)).json()["id"]

    for forged in (
        {"body": "hi", "sender_user_id": str(other_agent.id)},
        {"body": "hi", "recipient_user_id": str(other_agent.id)},
        {"body": "hi", "conversation_id": str(uuid.uuid4())},
    ):
        response = await client.post(
            f"{BASE}/{conversation_id}/messages",
            headers={"X-Test-User": agent.username},
            json=forged,
        )
        assert response.status_code == 422, forged

    # Starting a thread cannot name the participants either.
    for forged in (
        {"staff_user_id": str(other_agent.id)},
        {"owner_user_id": str(other_agent.id)},
    ):
        response = await client.post(
            BASE, headers={"X-Test-User": agent.username}, json=forged
        )
        assert response.status_code == 422, forged

    async with session_factory() as session:
        stored = (
            await session.exec(select(func.count()).select_from(StaffMessage))
        ).one()
    assert stored == 0

    # A legitimate message is attributed to the authenticated sender only.
    sent = await _send(client, agent, conversation_id, "legitimate")
    assert sent.status_code == 201
    assert sent.json()["sender_user_id"] == str(agent.id)
    notified = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": other_agent.username}
    )
    assert notified.status_code == 200
    assert all(
        n["type"] != NotificationType.STAFF_MESSAGE_RECEIVED.value
        for n in notified.json()
    )
    owner_notified = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": owner.username}
    )
    assert any(
        n["type"] == NotificationType.STAFF_MESSAGE_RECEIVED.value
        for n in owner_notified.json()
    )


@pytest.mark.asyncio
async def test_direct_messages_never_appear_in_ticket_comments(
    client, make_user, make_ticket
):
    """The private channel is separate from ticket comments and history."""
    await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    conversation_id = (await _start(client, agent)).json()["id"]
    secret = f"private-note-about-ticket-{ticket.ticket_number}"
    assert (await _send(client, agent, conversation_id, secret)).status_code == 201

    for viewer in (customer, agent):
        headers = {"X-Test-User": viewer.username}
        comments = await client.get(
            f"/api/v1/tickets/{ticket.id}/comments", headers=headers
        )
        assert comments.status_code == 200
        assert comments.json() == []

        detail = await client.get(f"/api/v1/tickets/{ticket.id}", headers=headers)
        assert secret not in detail.text

    history = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": agent.username},
    )
    assert history.status_code == 200
    assert secret not in history.text

    # Customers cannot see the private message through notifications either.
    customer_notifications = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": customer.username}
    )
    assert customer_notifications.status_code == 200
    assert secret not in customer_notifications.text
    assert all(
        n["type"]
        not in (
            NotificationType.STAFF_MESSAGE_RECEIVED.value,
            NotificationType.OWNER_MESSAGE_RECEIVED.value,
        )
        for n in customer_notifications.json()
    )
