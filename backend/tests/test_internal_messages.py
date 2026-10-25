"""Owner Inbox internal messaging.

These tests pin the backend-enforced rules, not just the UI:

* only the Owner composes broadcasts and browses the recipient directory;
* Only Owner/Agent/Admin are eligible; customers and the Owner are never
  recipients;
* a group message is stored once with one recipient row per addressed employee;
* an empty audience is an explicit error, never a silent success;
* a recipient only ever sees and can mark read their own message;
* the extended Owner inbox filters by sender role, sender and unread state.
"""

import uuid

import pytest
from sqlmodel import func, select

from app.enums.enums import Role
from app.models.internal_message import InternalMessage, InternalMessageRecipient

BASE = "/api/v1/internal-messages"
CONVERSATIONS = "/api/v1/staff-messages/conversations"


def _h(user):
    return {"X-Test-User": user.username}


async def _compose(
    client,
    owner,
    *,
    audience,
    subject="Announcement",
    body="Hello team",
    recipient_user_id=None,
):
    payload = {"audience": audience, "subject": subject, "body": body}
    if recipient_user_id is not None:
        payload["recipient_user_id"] = str(recipient_user_id)
    return await client.post(BASE, headers=_h(owner), json=payload)


# ---------------------------------------------------------------------------
# Compose + audience resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_broadcasts_to_all_agents(client, make_user, session_factory):
    owner = await make_user(role=Role.OWNER, username="the_owner")
    agent_a = await make_user(role=Role.AGENT, username="agent_a")
    agent_b = await make_user(role=Role.AGENT, username="agent_b")
    inactive_agent = await make_user(
        role=Role.AGENT, username="agent_off", is_active=False
    )
    admin = await make_user(role=Role.ADMIN, username="an_admin")
    customer = await make_user(username="a_customer")

    response = await _compose(client, owner, audience="agents")
    assert response.status_code == 201
    body = response.json()
    assert body["audience"] == "agents"
    assert body["recipient_count"] == 2
    assert body["read_count"] == 0

    async with session_factory() as session:
        message = (await session.exec(select(InternalMessage))).one()
        rows = (await session.exec(select(InternalMessageRecipient))).all()

    assert message.sender_user_id == owner.id
    assert len(rows) == 2
    recipients = {row.recipient_user_id for row in rows}
    assert recipients == {agent_a.id, agent_b.id}
    # Owner, inactive agent, admin and customer are all excluded.
    assert admin.id not in recipients
    assert customer.id not in recipients
    assert inactive_agent.id not in recipients
    # The role is snapshotted at send time.
    assert {row.recipient_role_snapshot for row in rows} == {Role.AGENT}


@pytest.mark.asyncio
async def test_owner_broadcasts_to_all_admins(client, make_user, session_factory):
    owner = await make_user(role=Role.OWNER)
    admin = await make_user(role=Role.ADMIN, username="admin_target")
    await make_user(role=Role.AGENT, username="agent_ignored")
    await make_user(username="customer_ignored")

    response = await _compose(client, owner, audience="admins")
    assert response.status_code == 201
    assert response.json()["recipient_count"] == 1

    async with session_factory() as session:
        rows = (await session.exec(select(InternalMessageRecipient))).all()
    assert {row.recipient_user_id for row in rows} == {admin.id}
    # The single Owner is never a recipient of their own broadcast.
    assert owner.id not in {row.recipient_user_id for row in rows}


@pytest.mark.asyncio
async def test_owner_broadcasts_to_everyone(client, make_user, session_factory):
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    await make_user(username="customer_excluded")

    response = await _compose(client, owner, audience="everyone")
    assert response.status_code == 201
    assert response.json()["recipient_count"] == 2

    async with session_factory() as session:
        rows = (await session.exec(select(InternalMessageRecipient))).all()
    assert {row.recipient_user_id for row in rows} == {agent.id, admin.id}


@pytest.mark.asyncio
async def test_owner_sends_individual_message_by_id(client, make_user, session_factory):
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT, username="target_agent")
    await make_user(role=Role.AGENT, username="other_agent")

    response = await _compose(
        client,
        owner,
        audience="individual",
        subject="One-to-one",
        body="Just for you",
        recipient_user_id=agent.id,
    )
    assert response.status_code == 201
    assert response.json()["audience"] == "individual"
    assert response.json()["recipient_count"] == 1

    async with session_factory() as session:
        rows = (await session.exec(select(InternalMessageRecipient))).all()
    assert len(rows) == 1
    assert rows[0].recipient_user_id == agent.id


@pytest.mark.asyncio
async def test_individual_message_needs_a_recipient(client, make_user):
    owner = await make_user(role=Role.OWNER)
    response = await _compose(client, owner, audience="individual")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_group_message_rejects_a_recipient_id(client, make_user):
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    response = await _compose(
        client, owner, audience="everyone", recipient_user_id=agent.id
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Empty + invalid recipients
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_agent_group_is_an_explicit_error(
    client, make_user, session_factory
):
    owner = await make_user(role=Role.OWNER)
    await make_user(role=Role.ADMIN)  # an admin exists, but no agent

    response = await _compose(client, owner, audience="agents")
    assert response.status_code == 409
    assert "no eligible recipients" in response.json()["detail"].lower()

    async with session_factory() as session:
        stored = (
            await session.exec(select(func.count()).select_from(InternalMessage))
        ).one()
    assert stored == 0  # never a silent success


@pytest.mark.asyncio
async def test_inactive_individual_recipient_is_rejected(
    client, make_user, session_factory
):
    owner = await make_user(role=Role.OWNER)
    inactive = await make_user(role=Role.AGENT, username="off_agent", is_active=False)

    response = await _compose(
        client, owner, audience="individual", recipient_user_id=inactive.id
    )
    assert response.status_code == 400

    async with session_factory() as session:
        stored = (
            await session.exec(select(func.count()).select_from(InternalMessage))
        ).one()
    assert stored == 0


@pytest.mark.asyncio
async def test_customer_and_owner_are_not_individual_recipients(client, make_user):
    owner = await make_user(role=Role.OWNER)
    customer = await make_user(username="cust_target")

    assert (
        await _compose(
            client, owner, audience="individual", recipient_user_id=customer.id
        )
    ).status_code == 400
    assert (
        await _compose(client, owner, audience="individual", recipient_user_id=owner.id)
    ).status_code == 400


@pytest.mark.asyncio
async def test_unknown_individual_recipient_is_not_found(client, make_user):
    owner = await make_user(role=Role.OWNER)
    response = await _compose(
        client, owner, audience="individual", recipient_user_id=uuid.uuid4()
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_owner_cannot_compose_or_browse(client, make_user):
    await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    target = await make_user(role=Role.AGENT, username="someone")

    for actor in (agent, admin):
        assert (await _compose(client, actor, audience="everyone")).status_code == 403
        assert (
            await client.get(f"{BASE}/recipients", headers=_h(actor))
        ).status_code == 403
        assert (await client.get(f"{BASE}/sent", headers=_h(actor))).status_code == 403
        # An employee cannot forge a direct message to another employee.
        assert (
            await _compose(
                client,
                actor,
                audience="individual",
                recipient_user_id=target.id,
            )
        ).status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_touch_any_internal_message_endpoint(client, make_user):
    owner = await make_user(role=Role.OWNER)
    await make_user(role=Role.AGENT, username="recipient_agent")
    customer = await make_user()
    sent = await _compose(client, owner, audience="everyone")
    assert sent.status_code == 201
    message_id = sent.json()["id"]

    assert (await client.get(BASE, headers=_h(customer))).status_code in (403, 405)
    assert (
        await client.get(f"{BASE}/recipients", headers=_h(customer))
    ).status_code == 403
    assert (await client.get(f"{BASE}/sent", headers=_h(customer))).status_code == 403
    assert (
        await client.get(f"{BASE}/received", headers=_h(customer))
    ).status_code == 403
    assert (
        await client.post(f"{BASE}/{message_id}/read", headers=_h(customer))
    ).status_code == 403


@pytest.mark.asyncio
async def test_spoofed_sender_field_is_rejected(client, make_user):
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)

    response = await client.post(
        BASE,
        headers=_h(owner),
        json={
            "audience": "individual",
            "recipient_user_id": str(agent.id),
            "subject": "hi",
            "body": "hi",
            "sender_user_id": str(agent.id),
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Recipient view + read tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_employee_only_sees_their_own_messages_and_can_mark_read(
    client, make_user
):
    owner = await make_user(role=Role.OWNER)
    alice = await make_user(role=Role.AGENT, username="alice_agent")
    bob = await make_user(role=Role.ADMIN, username="bob_admin")

    created = await _compose(
        client,
        owner,
        audience="individual",
        subject="For Alice",
        body="Secret",
        recipient_user_id=alice.id,
    )
    message_id = created.json()["id"]

    alice_inbox = await client.get(f"{BASE}/received", headers=_h(alice))
    assert alice_inbox.status_code == 200
    assert [m["subject"] for m in alice_inbox.json()] == ["For Alice"]
    assert alice_inbox.json()[0]["read_at"] is None

    # Bob was not addressed: he sees nothing and cannot mark it read.
    bob_inbox = await client.get(f"{BASE}/received", headers=_h(bob))
    assert bob_inbox.status_code == 200
    assert bob_inbox.json() == []
    assert (
        await client.post(f"{BASE}/{message_id}/read", headers=_h(bob))
    ).status_code == 404

    # Alice reads it.
    read = await client.post(f"{BASE}/{message_id}/read", headers=_h(alice))
    assert read.status_code == 200
    assert read.json() == {"updated": 1}
    # Idempotent: nothing left to update.
    assert (
        await client.post(f"{BASE}/{message_id}/read", headers=_h(alice))
    ).json() == {"updated": 0}

    after = await client.get(f"{BASE}/received", headers=_h(alice))
    assert after.json()[0]["read_at"] is not None


@pytest.mark.asyncio
async def test_received_detail_opens_the_exact_message_for_the_recipient_only(
    client, make_user
):
    owner = await make_user(role=Role.OWNER)
    alice = await make_user(role=Role.AGENT, username="detail_alice")
    bob = await make_user(role=Role.ADMIN, username="detail_bob")
    customer = await make_user(username="detail_customer")

    created = await _compose(
        client,
        owner,
        audience="individual",
        subject="Open me",
        body="The exact body",
        recipient_user_id=alice.id,
    )
    message_id = created.json()["id"]

    detail = await client.get(f"{BASE}/received/{message_id}", headers=_h(alice))
    assert detail.status_code == 200
    assert detail.json()["id"] == message_id
    assert detail.json()["subject"] == "Open me"
    assert detail.json()["body"] == "The exact body"
    assert detail.json()["read_at"] is None

    # Not a recipient: 404, never 403, so existence is not revealed.
    assert (
        await client.get(f"{BASE}/received/{message_id}", headers=_h(bob))
    ).status_code == 404
    # Customers cannot reach the internal-message surface at all.
    assert (
        await client.get(f"{BASE}/received/{message_id}", headers=_h(customer))
    ).status_code == 403
    assert (
        await client.get(f"{BASE}/received/{uuid.uuid4()}", headers=_h(alice))
    ).status_code == 404


@pytest.mark.asyncio
async def test_sent_view_reports_real_read_counts(client, make_user):
    owner = await make_user(role=Role.OWNER)
    alice = await make_user(role=Role.AGENT, username="count_alice")
    bob = await make_user(role=Role.AGENT, username="count_bob")

    created = await _compose(client, owner, audience="agents")
    message_id = created.json()["id"]

    detail = await client.get(f"{BASE}/sent/{message_id}", headers=_h(owner))
    assert detail.status_code == 200
    assert detail.json()["recipient_count"] == 2
    assert detail.json()["read_count"] == 0
    assert detail.json()["recipient_total"] == 2
    assert {r["recipient_user_id"] for r in detail.json()["recipients"]} == {
        str(alice.id),
        str(bob.id),
    }

    assert (
        await client.post(f"{BASE}/{message_id}/read", headers=_h(alice))
    ).status_code == 200

    detail_after = await client.get(f"{BASE}/sent/{message_id}", headers=_h(owner))
    assert detail_after.json()["read_count"] == 1

    sent = await client.get(f"{BASE}/sent", headers=_h(owner))
    assert sent.json()[0]["read_count"] == 1


@pytest.mark.asyncio
async def test_owner_cannot_read_another_senders_sent_detail(client, make_user):
    owner = await make_user(role=Role.OWNER)
    await make_user(role=Role.AGENT)
    created = await _compose(client, owner, audience="everyone")
    message_id = created.json()["id"]

    # A second owner cannot exist; use a non-owner to prove the 403, and a
    # random id to prove the 404 for an unknown message.
    agent = await make_user(role=Role.AGENT, username="probe_agent")
    assert (
        await client.get(f"{BASE}/sent/{message_id}", headers=_h(agent))
    ).status_code == 403


# ---------------------------------------------------------------------------
# Recipient search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recipient_search_by_name_email_and_account_id(client, make_user):
    owner = await make_user(role=Role.OWNER)
    alice = await make_user(
        role=Role.AGENT,
        username="alice_agent",
        email="alice@example.com",
    )
    await make_user(role=Role.ADMIN, username="bob_admin", email="bob@example.com")
    await make_user(username="customer_hidden", email="cust@example.com")

    # By name (case-insensitive substring).
    by_name = await client.get(f"{BASE}/recipients?q=alice", headers=_h(owner))
    assert by_name.status_code == 200
    assert {u["id"] for u in by_name.json()} == {str(alice.id)}

    # By email.
    by_email = await client.get(f"{BASE}/recipients?q=bob@", headers=_h(owner))
    assert {u["email"] for u in by_email.json()} == {"bob@example.com"}

    # By account id (a prefix of the UUID).
    by_id = await client.get(
        f"{BASE}/recipients?q={str(alice.id)[:8]}", headers=_h(owner)
    )
    assert {u["id"] for u in by_id.json()} == {str(alice.id)}

    # An unfiltered search lists agents and admins, never a customer.
    everyone = await client.get(f"{BASE}/recipients", headers=_h(owner))
    assert "customer_hidden" not in {u["username"] for u in everyone.json()}

    # Role filter.
    admins = await client.get(f"{BASE}/recipients?role=admin", headers=_h(owner))
    assert {u["role"] for u in admins.json()} == {"admin"}

    # A non-staff role is rejected outright.
    assert (
        await client.get(f"{BASE}/recipients?role=customer", headers=_h(owner))
    ).status_code == 422


# ---------------------------------------------------------------------------
# Sent filtering + pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sent_filters_and_pagination(client, make_user):
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT, username="paging_agent")
    await make_user(role=Role.ADMIN, username="paging_admin")

    await _compose(client, owner, audience="agents", subject="To agents")
    await _compose(client, owner, audience="admins", subject="To admins")
    await _compose(
        client,
        owner,
        audience="individual",
        subject="Direct",
        recipient_user_id=agent.id,
    )

    all_sent = await client.get(f"{BASE}/sent?limit=100", headers=_h(owner))
    assert len(all_sent.json()) == 3

    agents_only = await client.get(f"{BASE}/sent?audience=agents", headers=_h(owner))
    assert [m["audience"] for m in agents_only.json()] == ["agents"]

    searched = await client.get(f"{BASE}/sent?q=direct", headers=_h(owner))
    assert [m["subject"] for m in searched.json()] == ["Direct"]

    page = await client.get(f"{BASE}/sent?limit=2&offset=0", headers=_h(owner))
    page_two = await client.get(f"{BASE}/sent?limit=2&offset=2", headers=_h(owner))
    assert len(page.json()) == 2
    assert len(page_two.json()) == 1


# ---------------------------------------------------------------------------
# Extended staff-conversation inbox (Owner filters + received preview)
# ---------------------------------------------------------------------------


async def _start(client, user, subject=None):
    return await client.post(
        CONVERSATIONS,
        headers=_h(user),
        json={} if subject is None else {"subject": subject},
    )


async def _send(client, user, conversation_id, body):
    return await client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        headers=_h(user),
        json={"body": body},
    )


@pytest.mark.asyncio
async def test_owner_inbox_reports_sender_role_and_filters(client, make_user):
    owner = await make_user(role=Role.OWNER, username="owner_filters")
    agent = await make_user(role=Role.AGENT, username="filter_agent")
    admin = await make_user(role=Role.ADMIN, username="filter_admin")

    agent_thread = (await _start(client, agent, subject="From an agent")).json()["id"]
    admin_thread = (await _start(client, admin, subject="From an admin")).json()["id"]
    await _send(client, agent, agent_thread, "agent message")

    inbox = await client.get(CONVERSATIONS, headers=_h(owner))
    assert inbox.status_code == 200
    roles = {c["staff_user_id"]: c["staff_role"] for c in inbox.json()}
    assert roles[str(agent.id)] == "agent"
    assert roles[str(admin.id)] == "admin"

    agents = await client.get(f"{CONVERSATIONS}?staff_role=agent", headers=_h(owner))
    assert {c["id"] for c in agents.json()} == {agent_thread}

    one_sender = await client.get(
        f"{CONVERSATIONS}?staff_user_id={admin.id}", headers=_h(owner)
    )
    assert {c["id"] for c in one_sender.json()} == {admin_thread}

    unread = await client.get(f"{CONVERSATIONS}?unread_only=true", headers=_h(owner))
    assert {c["id"] for c in unread.json()} == {agent_thread}

    # An agent still only ever sees their own thread.
    agent_view = await client.get(
        f"{CONVERSATIONS}?staff_role=admin", headers=_h(agent)
    )
    assert {c["id"] for c in agent_view.json()} == {agent_thread}


@pytest.mark.asyncio
async def test_owner_inbox_preview_is_the_message_received_not_the_reply(
    client, make_user
):
    owner = await make_user(role=Role.OWNER, username="owner_preview")
    agent = await make_user(role=Role.AGENT, username="preview_agent")

    conversation_id = (await _start(client, agent)).json()["id"]
    await _send(client, agent, conversation_id, "the agent asks for help")
    await _send(client, owner, conversation_id, "the owner replies")

    inbox = await client.get(CONVERSATIONS, headers=_h(owner))
    row = inbox.json()[0]
    assert row["last_received_preview"] == "the agent asks for help"
    assert row["last_received_at"] is not None


@pytest.mark.asyncio
async def test_agent_and_admin_message_the_owner_through_the_thread(client, make_user):
    owner = await make_user(role=Role.OWNER, username="thread_owner")
    agent = await make_user(role=Role.AGENT, username="thread_agent")
    admin = await make_user(role=Role.ADMIN, username="thread_admin")

    agent_thread = (await _start(client, agent, subject="Agent to owner")).json()["id"]
    admin_thread = (await _start(client, admin, subject="Admin to owner")).json()["id"]
    assert (
        await _send(client, agent, agent_thread, "agent to owner")
    ).status_code == 201
    assert (
        await _send(client, admin, admin_thread, "admin to owner")
    ).status_code == 201

    owner_inbox = await client.get(CONVERSATIONS, headers=_h(owner))
    assert {c["id"] for c in owner_inbox.json()} == {agent_thread, admin_thread}
    assert all(c["unread_count"] == 1 for c in owner_inbox.json())
