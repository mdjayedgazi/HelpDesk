"""Universal staff-to-staff private messaging.

The authorization rules are enforced in the backend, not just hidden in the UI:

* CUSTOMERs cannot read, start, search, send, or mark read - every endpoint
  answers ``403`` from the role dependency;
* any two eligible staff members (AGENT/ADMIN/OWNER) can hold a 1:1 thread;
* an employee only ever sees conversations they participate in; another
  employee's thread is ``404`` (not ``403``) so its existence is not revealed;
* recipients are validated server-side and are never taken from the body when
  reading/replying (they come from the conversation).
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


async def _start(client, user, recipient, subject=None):
    payload: dict = {"recipient_user_id": str(recipient.id)}
    if subject is not None:
        payload["subject"] = subject
    return await client.post(BASE, headers={"X-Test-User": user.username}, json=payload)


async def _send(client, user, conversation_id, body, mentions=None):
    payload: dict = {"body": body}
    if mentions is not None:
        payload["mentioned_user_ids"] = [str(m) for m in mentions]
    return await client.post(
        f"{BASE}/{conversation_id}/messages",
        headers={"X-Test-User": user.username},
        json=payload,
    )


@pytest.mark.asyncio
async def test_customer_is_denied_everywhere(client, make_user):
    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    other = await make_user(role=Role.ADMIN)
    conversation_id = (await _start(client, agent, other)).json()["id"]

    headers = {"X-Test-User": customer.username}
    assert (await client.get(BASE, headers=headers)).status_code == 403
    assert (
        await client.get("/api/v1/staff-messages/directory", headers=headers)
    ).status_code == 403
    assert (await _start(client, customer, agent)).status_code == 403
    assert (
        await client.get(f"{BASE}/{conversation_id}", headers=headers)
    ).status_code == 403
    assert (await _send(client, customer, conversation_id, "hello?")).status_code == 403
    assert (
        await client.post(f"{BASE}/{conversation_id}/read", headers=headers)
    ).status_code == 403


@pytest.mark.asyncio
async def test_any_two_staff_members_can_message(client, make_user):
    """Every eligible pairing is allowed: owner/admin/agent in all directions."""
    owner = await make_user(role=Role.OWNER, username="pair_owner")
    admin = await make_user(role=Role.ADMIN, username="pair_admin")
    agent_a = await make_user(role=Role.AGENT, username="pair_agent_a")
    agent_b = await make_user(role=Role.AGENT, username="pair_agent_b")

    for sender, recipient in (
        (owner, admin),
        (owner, agent_a),
        (admin, owner),
        (admin, agent_a),
        (agent_a, owner),
        (agent_a, admin),
        (agent_a, agent_b),
    ):
        started = await _start(client, sender, recipient)
        assert started.status_code == 200, (sender.username, recipient.username)
        conversation_id = started.json()["id"]
        sent = await _send(client, sender, conversation_id, "hello")
        assert sent.status_code == 201


@pytest.mark.asyncio
async def test_pair_maps_to_one_conversation_regardless_of_starter(client, make_user):
    agent = await make_user(role=Role.AGENT, username="pair_canon_a")
    other = await make_user(role=Role.ADMIN, username="pair_canon_b")

    first = await _start(client, agent, other, subject="From agent")
    second = await _start(client, other, agent, subject="From admin")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["subject"] == "From agent"


@pytest.mark.asyncio
async def test_self_conversation_is_rejected(client, make_user):
    agent = await make_user(role=Role.AGENT)
    response = await _start(client, agent, agent)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_customer_recipient_is_rejected(client, make_user):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    response = await _start(client, agent, customer)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_inactive_employee_recipient_is_rejected(client, make_user):
    agent = await make_user(role=Role.AGENT)
    inactive = await make_user(role=Role.AGENT, is_active=False)
    response = await _start(client, agent, inactive)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unknown_recipient_is_not_found(client, make_user):
    agent = await make_user(role=Role.AGENT)
    response = await client.post(
        BASE,
        headers={"X-Test-User": agent.username},
        json={"recipient_user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_employee_cannot_read_another_conversation(client, make_user):
    """Participant isolation: list/detail/reply/read are scoped to the pair."""
    alice = await make_user(role=Role.AGENT, username="iso_alice")
    bob = await make_user(role=Role.AGENT, username="iso_bob")
    carol = await make_user(role=Role.AGENT, username="iso_carol")

    alice_bob = (await _start(client, alice, bob)).json()["id"]
    bob_carol = (await _start(client, bob, carol)).json()["id"]
    assert alice_bob != bob_carol

    carol_headers = {"X-Test-User": carol.username}
    listed = await client.get(BASE, headers=carol_headers)
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [bob_carol]

    assert (
        await client.get(f"{BASE}/{alice_bob}", headers=carol_headers)
    ).status_code == 404
    assert (
        await _send(client, carol, alice_bob, "reading your mail")
    ).status_code == 404
    assert (
        await client.post(f"{BASE}/{alice_bob}/read", headers=carol_headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_message_flow_notifications_and_read_tracking(
    client, make_user, session_factory
):
    sender = await make_user(role=Role.AGENT, username="flow_sender")
    recipient = await make_user(role=Role.ADMIN, username="flow_recipient")

    conversation_id = (
        await _start(client, sender, recipient, subject="Escalation")
    ).json()["id"]

    sent = await _send(client, sender, conversation_id, "Can you review ticket #10042?")
    assert sent.status_code == 201
    message = sent.json()
    assert message["sender_user_id"] == str(sender.id)
    assert message["read_at"] is None

    # The recipient is notified, without leaking the message body.
    async with session_factory() as session:
        notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == recipient.id,
                    Notification.type == NotificationType.STAFF_MESSAGE_RECEIVED,
                )
            )
        ).all()
    assert len(notifications) == 1
    assert str(notifications[0].related_conversation_id) == conversation_id
    assert "10042" not in notifications[0].message

    recipient_headers = {"X-Test-User": recipient.username}
    inbox = await client.get(BASE, headers=recipient_headers)
    assert inbox.status_code == 200
    assert len(inbox.json()) == 1
    assert inbox.json()[0]["unread_count"] == 1

    reply = await _send(client, recipient, conversation_id, "Reviewing it now.")
    assert reply.status_code == 201

    async with session_factory() as session:
        reply_notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == sender.id,
                    Notification.type == NotificationType.STAFF_MESSAGE_RECEIVED,
                )
            )
        ).all()
    assert len(reply_notifications) == 1

    sender_headers = {"X-Test-User": sender.username}
    sender_inbox = await client.get(BASE, headers=sender_headers)
    assert sender_inbox.json()[0]["unread_count"] == 1
    assert sender_inbox.json()[0]["message_count"] == 2
    assert sender_inbox.json()[0]["last_message_preview"] == "Reviewing it now."

    detail = await client.get(f"{BASE}/{conversation_id}", headers=sender_headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2

    read = await client.post(f"{BASE}/{conversation_id}/read", headers=sender_headers)
    assert read.status_code == 200
    assert read.json() == {"updated": 1}

    after = await client.get(BASE, headers=sender_headers)
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
    assert by_sender[recipient.id].read_at is not None
    assert by_sender[sender.id].read_at is None


@pytest.mark.asyncio
async def test_conversation_list_is_scoped_to_the_participant(client, make_user):
    owner = await make_user(role=Role.OWNER, username="scope_owner")
    agent = await make_user(role=Role.AGENT, username="scope_agent")
    admin = await make_user(role=Role.ADMIN, username="scope_admin")

    agent_thread = (await _start(client, agent, owner)).json()["id"]
    admin_thread = (await _start(client, admin, owner)).json()["id"]

    owner_inbox = await client.get(BASE, headers={"X-Test-User": owner.username})
    assert owner_inbox.status_code == 200
    assert {c["id"] for c in owner_inbox.json()} == {agent_thread, admin_thread}

    agent_inbox = await client.get(BASE, headers={"X-Test-User": agent.username})
    assert {c["id"] for c in agent_inbox.json()} == {agent_thread}


@pytest.mark.asyncio
async def test_conversation_list_is_paginated(client, make_user):
    owner = await make_user(role=Role.OWNER, username="page_owner")
    agents = [
        await make_user(role=Role.AGENT, username=f"page_agent_{index}")
        for index in range(3)
    ]
    for agent in agents:
        assert (await _start(client, agent, owner)).status_code == 200

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
async def test_conversation_summaries_do_not_issue_n_plus_one_queries(
    client, make_user, session_factory
):
    owner = await make_user(role=Role.OWNER, username="n1_owner")
    for index in range(4):
        agent = await make_user(role=Role.AGENT, username=f"n1_agent_{index}")
        conversation_id = (await _start(client, agent, owner)).json()["id"]
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
    assert len(statements) <= 6, "\n\n".join(statements)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["", "   ", "\n\t ", "x" * 5001])
async def test_invalid_message_bodies_rejected(client, make_user, body):
    sender = await make_user(role=Role.AGENT)
    recipient = await make_user(role=Role.ADMIN)
    conversation_id = (await _start(client, sender, recipient)).json()["id"]
    assert (await _send(client, sender, conversation_id, body)).status_code == 422


@pytest.mark.asyncio
async def test_message_body_is_trimmed(client, make_user):
    sender = await make_user(role=Role.AGENT)
    recipient = await make_user(role=Role.ADMIN)
    conversation_id = (await _start(client, sender, recipient)).json()["id"]
    response = await _send(client, sender, conversation_id, "  padded  ")
    assert response.status_code == 201
    assert response.json()["body"] == "padded"


@pytest.mark.asyncio
async def test_duplicate_thread_creation_is_impossible(
    client, make_user, session_factory
):
    sender = await make_user(role=Role.AGENT)
    recipient = await make_user(role=Role.ADMIN)

    first = await _start(client, sender, recipient)
    second = await _start(client, sender, recipient)
    assert first.json()["id"] == second.json()["id"]

    async with session_factory() as session:
        count = (
            await session.exec(select(func.count()).select_from(StaffConversation))
        ).one()
    assert count == 1


@pytest.mark.asyncio
async def test_unknown_conversation_is_not_found(client, make_user):
    agent = await make_user(role=Role.AGENT)
    response = await client.get(
        f"{BASE}/{uuid.uuid4()}", headers={"X-Test-User": agent.username}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_spoofed_sender_and_participant_ids_are_rejected(
    client, make_user, session_factory
):
    """The sender is the authenticated user; the pair comes from the thread."""
    sender = await make_user(role=Role.AGENT, username="spoof_sender")
    recipient = await make_user(role=Role.ADMIN, username="spoof_recipient")
    other = await make_user(role=Role.AGENT, username="spoof_other")
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    for forged in (
        {"body": "hi", "sender_user_id": str(other.id)},
        {"body": "hi", "recipient_user_id": str(other.id)},
        {"body": "hi", "conversation_id": str(uuid.uuid4())},
    ):
        response = await client.post(
            f"{BASE}/{conversation_id}/messages",
            headers={"X-Test-User": sender.username},
            json=forged,
        )
        assert response.status_code == 422, forged

    # Starting a thread cannot name the participants directly.
    for forged in (
        {"staff_user_id": str(other.id)},
        {"owner_user_id": str(other.id)},
    ):
        response = await client.post(
            BASE, headers={"X-Test-User": sender.username}, json=forged
        )
        assert response.status_code == 422, forged

    async with session_factory() as session:
        stored = (
            await session.exec(select(func.count()).select_from(StaffMessage))
        ).one()
    assert stored == 0

    sent = await _send(client, sender, conversation_id, "legitimate")
    assert sent.status_code == 201
    assert sent.json()["sender_user_id"] == str(sender.id)
    notified = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": other.username}
    )
    assert notified.status_code == 200
    assert all(
        n["type"] != NotificationType.STAFF_MESSAGE_RECEIVED.value
        for n in notified.json()
    )
    recipient_notified = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": recipient.username}
    )
    assert any(
        n["type"] == NotificationType.STAFF_MESSAGE_RECEIVED.value
        for n in recipient_notified.json()
    )


@pytest.mark.asyncio
async def test_direct_messages_never_appear_in_ticket_comments(
    client, make_user, make_ticket
):
    sender = await make_user(role=Role.AGENT, username="private_sender")
    recipient = await make_user(role=Role.ADMIN, username="private_recipient")
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=sender)

    conversation_id = (await _start(client, sender, recipient)).json()["id"]
    secret = f"private-note-about-ticket-{ticket.ticket_number}"
    assert (await _send(client, sender, conversation_id, secret)).status_code == 201

    for viewer in (customer, sender):
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
        headers={"X-Test-User": sender.username},
    )
    assert history.status_code == 200
    assert secret not in history.text

    customer_notifications = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": customer.username}
    )
    assert customer_notifications.status_code == 200
    assert secret not in customer_notifications.text
    assert all(
        n["type"] != NotificationType.STAFF_MESSAGE_RECEIVED.value
        for n in customer_notifications.json()
    )
