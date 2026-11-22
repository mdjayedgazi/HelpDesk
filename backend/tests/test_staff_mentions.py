"""Staff directory search, structured @mentions, and authorization.

Covers the universal messaging additions:

* the staff directory endpoint (case-insensitive search across name/username/id,
  active staff only, customer excluded, ordering);
* structured mentions persisted as real user references;
* mention validation (unknown / inactive / customer / self rejected);
* mention notifications (only after persistence, deduped, no customer, no
  duplicate for the same message);
* role permission matrix for messaging operations.
"""

import uuid

import pytest
from sqlmodel import select

from app.enums.enums import NotificationType, Role
from app.models.internal_message import InternalMessageMention
from app.models.staff_message import StaffMessage, StaffMessageMention

CONVERSATIONS = "/api/v1/staff-messages/conversations"
DIRECTORY = "/api/v1/staff-messages/directory"
INTERNAL = "/api/v1/internal-messages"


def _h(user):
    return {"X-Test-User": user.username}


async def _start(client, sender, recipient):
    return await client.post(
        CONVERSATIONS,
        headers=_h(sender),
        json={"recipient_user_id": str(recipient.id)},
    )


async def _send(client, sender, conversation_id, body, mentions=None):
    payload: dict = {"body": body}
    if mentions is not None:
        payload["mentioned_user_ids"] = [str(m) for m in mentions]
    return await client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages",
        headers=_h(sender),
        json=payload,
    )


# ---------------------------------------------------------------------------
# Directory search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_directory_returns_active_staff_only(client, make_user):
    viewer = await make_user(role=Role.AGENT, username="dir_viewer")
    owner = await make_user(role=Role.OWNER, username="dir_owner")
    admin = await make_user(role=Role.ADMIN, username="dir_admin")
    agent = await make_user(role=Role.AGENT, username="dir_agent")
    customer = await make_user(username="dir_customer")
    inactive = await make_user(
        role=Role.AGENT, username="dir_inactive", is_active=False
    )

    response = await client.get(DIRECTORY, headers=_h(viewer))
    assert response.status_code == 200
    ids = {u["id"] for u in response.json()}
    assert str(owner.id) in ids
    assert str(admin.id) in ids
    assert str(agent.id) in ids
    # Customers, inactive accounts and the caller are excluded.
    assert str(customer.id) not in ids
    assert str(inactive.id) not in ids
    assert str(viewer.id) not in ids


@pytest.mark.asyncio
async def test_directory_customer_is_forbidden(client, make_user):
    customer = await make_user()
    response = await client.get(DIRECTORY, headers=_h(customer))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_directory_every_staff_role_can_search(client, make_user):
    owner = await make_user(role=Role.OWNER, username="dir_search_owner")
    admin = await make_user(role=Role.ADMIN, username="dir_search_admin")
    agent = await make_user(role=Role.AGENT, username="dir_search_agent")
    for viewer in (owner, admin, agent):
        response = await client.get(DIRECTORY, headers=_h(viewer))
        assert response.status_code == 200, viewer.username


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "term", ["alice", "ALICE", "Alice", "ali", "ALI", "@alice", "@Alice"]
)
async def test_directory_search_is_case_insensitive(client, make_user, term):
    viewer = await make_user(role=Role.AGENT, username="ci_viewer")
    await make_user(
        role=Role.AGENT,
        username="alice_chen",
        full_name="Alice Chen",
        email="alice.chen@example.com",
    )

    response = await client.get(DIRECTORY, headers=_h(viewer), params={"q": term})
    assert response.status_code == 200
    usernames = {u["username"] for u in response.json()}
    assert "alice_chen" in usernames


@pytest.mark.asyncio
async def test_directory_search_by_partial_and_prefix(client, make_user):
    viewer = await make_user(role=Role.AGENT, username="part_viewer")
    await make_user(role=Role.AGENT, username="alicia_keys", full_name="Alicia Keys")
    await make_user(role=Role.AGENT, username="malik_owens", full_name="Malik Owens")

    # "ali" matches Alicia; "lic" matches inside the name/username too.
    for term in ("ali", "lic"):
        response = await client.get(DIRECTORY, headers=_h(viewer), params={"q": term})
        assert response.status_code == 200
        assert any(u["username"] == "alicia_keys" for u in response.json()), term


@pytest.mark.asyncio
async def test_directory_exact_username_ranks_first(client, make_user):
    viewer = await make_user(role=Role.AGENT, username="rank_viewer")
    await make_user(role=Role.AGENT, username="alice_secondary", full_name="Zoe Alice")
    await make_user(role=Role.AGENT, username="alice", full_name="Alice Primary")

    response = await client.get(DIRECTORY, headers=_h(viewer), params={"q": "alice"})
    assert response.status_code == 200
    assert response.json()[0]["username"] == "alice"


@pytest.mark.asyncio
async def test_directory_search_by_account_id(client, make_user):
    viewer = await make_user(role=Role.AGENT, username="id_viewer")
    target = await make_user(role=Role.ADMIN, username="id_target")

    response = await client.get(
        DIRECTORY, headers=_h(viewer), params={"q": str(target.id)[:8]}
    )
    assert response.status_code == 200
    assert any(u["id"] == str(target.id) for u in response.json())


# ---------------------------------------------------------------------------
# Structured mentions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mention_is_persisted_as_real_user_reference(
    client, make_user, session_factory
):
    sender = await make_user(role=Role.AGENT, username="mention_sender")
    recipient = await make_user(role=Role.ADMIN, username="mention_recipient")
    mentioned = await make_user(role=Role.AGENT, username="mention_target")
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    response = await _send(
        client,
        sender,
        conversation_id,
        "Hello @mention_target, please review.",
        [mentioned.id],
    )
    assert response.status_code == 201
    assert str(mentioned.id) in {str(m) for m in response.json()["mentioned_user_ids"]}

    async with session_factory() as session:
        rows = (await session.exec(select(StaffMessageMention))).all()
    assert len(rows) == 1
    assert rows[0].mentioned_user_id == mentioned.id

    # The mention is also returned on the conversation detail.
    detail = await client.get(f"{CONVERSATIONS}/{conversation_id}", headers=_h(sender))
    message = detail.json()["messages"][0]
    assert str(mentioned.id) in {str(m) for m in message["mentioned_user_ids"]}


@pytest.mark.asyncio
async def test_duplicate_mentions_in_one_message_are_stored_once(
    client, make_user, session_factory
):
    sender = await make_user(role=Role.AGENT, username="dup_sender")
    recipient = await make_user(role=Role.AGENT, username="dup_recipient")
    mentioned = await make_user(role=Role.AGENT, username="dup_target")
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    response = await _send(
        client,
        sender,
        conversation_id,
        "@dup_target and again @dup_target",
        [mentioned.id, mentioned.id],
    )
    assert response.status_code == 201
    async with session_factory() as session:
        rows = (await session.exec(select(StaffMessageMention))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_unknown_mention_is_rejected(client, make_user, session_factory):
    sender = await make_user(role=Role.AGENT)
    recipient = await make_user(role=Role.AGENT)
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    response = await _send(client, sender, conversation_id, "hi @ghost", [uuid.uuid4()])
    assert response.status_code == 422
    async with session_factory() as session:
        assert (await session.exec(select(StaffMessage))).all() == []


@pytest.mark.asyncio
async def test_inactive_or_customer_mention_is_rejected(client, make_user):
    sender = await make_user(role=Role.AGENT)
    recipient = await make_user(role=Role.AGENT)
    inactive = await make_user(role=Role.AGENT, is_active=False)
    customer = await make_user()
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    assert (
        await _send(client, sender, conversation_id, "hi", [inactive.id])
    ).status_code == 422
    assert (
        await _send(client, sender, conversation_id, "hi", [customer.id])
    ).status_code == 422


@pytest.mark.asyncio
async def test_self_mention_is_rejected(client, make_user):
    sender = await make_user(role=Role.AGENT)
    recipient = await make_user(role=Role.AGENT)
    conversation_id = (await _start(client, sender, recipient)).json()["id"]
    assert (
        await _send(client, sender, conversation_id, "hi", [sender.id])
    ).status_code == 422


# ---------------------------------------------------------------------------
# Mention notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mention_notifies_the_counterpart_as_a_mention(client, make_user):
    """The participant who can open the message is notified once, as a mention."""
    sender = await make_user(role=Role.AGENT, username="mn_sender")
    recipient = await make_user(role=Role.AGENT, username="mn_recipient")
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    assert (
        await _send(
            client, sender, conversation_id, "@mn_recipient please look", [recipient.id]
        )
    ).status_code == 201

    notes = await client.get("/api/v1/notifications", headers=_h(recipient))
    assert notes.status_code == 200
    mention_notes = [
        n for n in notes.json() if n["type"] == NotificationType.STAFF_MENTION.value
    ]
    assert len(mention_notes) == 1
    assert mention_notes[0]["related_conversation_id"] == conversation_id
    # Exactly one alert for the message, not a mention plus a message alert.
    assert len(notes.json()) == 1


@pytest.mark.asyncio
async def test_third_party_mention_is_stored_but_not_notified(
    client, make_user, session_factory
):
    """A non-participant cannot open a 1:1 thread, so they are not notified.

    The structured mention row is still stored (so the body renders), but a
    notification would 404 on open and leak the private thread's existence, so
    none is created.
    """
    sender = await make_user(role=Role.AGENT, username="mn3p_sender")
    recipient = await make_user(role=Role.AGENT, username="mn3p_recipient")
    third = await make_user(role=Role.ADMIN, username="mn3p_third")
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    assert (
        await _send(client, sender, conversation_id, "@mn3p_third fyi", [third.id])
    ).status_code == 201

    async with session_factory() as session:
        rows = (await session.exec(select(StaffMessageMention))).all()
    assert any(r.mentioned_user_id == third.id for r in rows)

    notes = await client.get("/api/v1/notifications", headers=_h(third))
    assert notes.status_code == 200
    assert all(n["type"] != NotificationType.STAFF_MENTION.value for n in notes.json())


@pytest.mark.asyncio
async def test_unmentioned_counterpart_gets_a_plain_message_notification(
    client, make_user
):
    sender = await make_user(role=Role.AGENT, username="plain_sender")
    recipient = await make_user(role=Role.AGENT, username="plain_recipient")
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    assert (
        await _send(client, sender, conversation_id, "no mentions here")
    ).status_code == 201

    notes = await client.get("/api/v1/notifications", headers=_h(recipient))
    types = [n["type"] for n in notes.json()]
    assert types == [NotificationType.STAFF_MESSAGE_RECEIVED.value]


@pytest.mark.asyncio
async def test_customer_never_receives_mention_notifications(client, make_user):
    sender = await make_user(role=Role.AGENT, username="mn3_sender")
    recipient = await make_user(role=Role.AGENT, username="mn3_recipient")
    customer = await make_user()
    conversation_id = (await _start(client, sender, recipient)).json()["id"]

    await _send(client, sender, conversation_id, "internal only")

    # Customers cannot even list conversations; their notification list is
    # purely their own ticket activity, never internal mentions.
    notes = await client.get("/api/v1/notifications", headers=_h(customer))
    assert notes.status_code == 200
    assert all(n["type"] != NotificationType.STAFF_MENTION.value for n in notes.json())


# ---------------------------------------------------------------------------
# Internal (Owner Inbox) compose mentions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_compose_persists_mentions_and_notifies_without_duplicates(
    client, make_user, session_factory
):
    owner = await make_user(role=Role.OWNER, username="compose_owner")
    mentioned = await make_user(role=Role.AGENT, username="compose_target")

    response = await client.post(
        INTERNAL,
        headers=_h(owner),
        json={
            "audience": "individual",
            "recipient_user_id": str(mentioned.id),
            "subject": "Heads up",
            "body": "@compose_target see below",
            "mentioned_user_ids": [str(mentioned.id)],
        },
    )
    assert response.status_code == 201

    async with session_factory() as session:
        mention_rows = (await session.exec(select(InternalMessageMention))).all()
    assert len(mention_rows) == 1
    assert mention_rows[0].mentioned_user_id == mentioned.id

    # The recipient is also the mentioned employee: exactly one notification
    # total, typed as a mention (never a duplicate internal-message alert).
    notes = await client.get("/api/v1/notifications", headers=_h(mentioned))
    types = [n["type"] for n in notes.json()]
    assert len(types) == 1
    assert types.count(NotificationType.STAFF_MENTION.value) == 1
    assert types.count(NotificationType.INTERNAL_MESSAGE_RECEIVED.value) == 0


@pytest.mark.asyncio
async def test_owner_compose_rejects_invalid_mention(client, make_user):
    owner = await make_user(role=Role.OWNER, username="compose_owner2")
    customer = await make_user()

    response = await client.post(
        INTERNAL,
        headers=_h(owner),
        json={
            "audience": "everyone",
            "subject": "Bad mention",
            "body": "hello",
            "mentioned_user_ids": [str(customer.id)],
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Role permission matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_role_permission_matrix(client, make_user):
    owner = await make_user(role=Role.OWNER, username="matrix_owner")
    admin = await make_user(role=Role.ADMIN, username="matrix_admin")
    agent = await make_user(role=Role.AGENT, username="matrix_agent")
    customer = await make_user()

    # Open messaging (list) - staff yes, customer no.
    for staff in (owner, admin, agent):
        assert (await client.get(CONVERSATIONS, headers=_h(staff))).status_code == 200
    assert (await client.get(CONVERSATIONS, headers=_h(customer))).status_code == 403

    # Search eligible staff - staff yes, customer no.
    for staff in (owner, admin, agent):
        assert (await client.get(DIRECTORY, headers=_h(staff))).status_code == 200
    assert (await client.get(DIRECTORY, headers=_h(customer))).status_code == 403

    # Start a conversation - staff yes, customer no.
    assert (await _start(client, owner, admin)).status_code == 200
    assert (await _start(client, admin, agent)).status_code == 200
    assert (await _start(client, agent, owner)).status_code == 200
    assert (await _start(client, customer, agent)).status_code == 403
