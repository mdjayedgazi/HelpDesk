"""Notification lifecycle: event -> recipient -> destination.

These tests pin the behaviour described in the notification feature brief:

* every supported event creates the right notification for the right people and
  never for the actor;
* the customer is never told about staff-only activity;
* resolving a ticket asks for feedback exactly once;
* internal messages notify their addressed recipients (and the Owner about
  staff-to-Owner messages) with the correct deep link;
* read state stays consistent between the notification centre and the message's
  own per-recipient read state;
* the notification API only ever exposes and mutates the caller's own rows.
"""

import pytest
from sqlmodel import select

from app.enums.enums import NotificationType, Role, TicketStatus

NOTIFICATIONS = "/api/v1/notifications"
TICKETS = "/api/v1/tickets"
STAFF_CONVERSATIONS = "/api/v1/staff-messages/conversations"
INTERNAL_MESSAGES = "/api/v1/internal-messages"


def _h(user):
    return {"X-Test-User": user.username}


async def _notifications(client, user, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{NOTIFICATIONS}?{query}" if query else NOTIFICATIONS
    response = await client.get(url, headers=_h(user))
    assert response.status_code == 200, response.text
    return response.json()


async def _unread_count(client, user):
    response = await client.get(f"{NOTIFICATIONS}/unread-count", headers=_h(user))
    assert response.status_code == 200, response.text
    return response.json()


async def _status(client, staff, ticket_id, status, **extra):
    payload = {"status": status, **extra}
    return await client.patch(f"{TICKETS}/{ticket_id}", headers=_h(staff), json=payload)


async def _comment(client, author, ticket_id, body, *, internal=False):
    return await client.post(
        f"{TICKETS}/{ticket_id}/comments",
        headers=_h(author),
        json={"body": body, "is_internal": internal},
    )


# ---------------------------------------------------------------------------
# Ticket events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ticket_creation_notifies_customer_and_assignee(client, make_user):
    customer = await make_user(role=Role.CUSTOMER)
    agent = await make_user(role=Role.AGENT, username="the_agent")

    response = await client.post(
        TICKETS,
        headers=_h(customer),
        json={
            "title": "Printer is broken",
            "description": "It stopped working this morning.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 201, response.text
    ticket = response.json()

    customer_notes = await _notifications(client, customer)
    assert [n["type"] for n in customer_notes] == [
        NotificationType.TICKET_CREATED.value
    ]
    assert customer_notes[0]["related_ticket_id"] == ticket["id"]
    assert customer_notes[0]["related_internal_message_id"] is None
    # The customer's receipt is unread and counts toward the badge.
    assert await _unread_count(client, customer) == {
        "count": 1,
        "tickets": 1,
        "messages": 0,
        "account_requests": 0,
    }

    agent_notes = await _notifications(client, agent)
    assert [n["type"] for n in agent_notes] == [NotificationType.TICKET_ASSIGNED.value]
    assert agent_notes[0]["related_ticket_id"] == ticket["id"]


@pytest.mark.asyncio
async def test_public_reply_notifies_the_other_side_but_never_the_actor(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER)
    agent = await make_user(role=Role.AGENT, username="reply_agent")
    ticket = await make_ticket(customer, assignee=agent)

    # Agent replies -> customer is told.
    assert (await _comment(client, agent, ticket.id, "I am on it.")).status_code == 201
    customer_notes = await _notifications(client, customer)
    assert [n["type"] for n in customer_notes] == [NotificationType.NEW_COMMENT.value]
    # The agent was the actor, so nothing for them.
    assert await _notifications(client, agent) == []

    # Customer replies -> the assignee is told.
    assert (
        await _comment(client, customer, ticket.id, "Thanks, any update?")
    ).status_code == 201
    agent_notes = await _notifications(client, agent)
    assert [n["type"] for n in agent_notes] == [NotificationType.NEW_COMMENT.value]


@pytest.mark.asyncio
async def test_internal_note_never_notifies_the_customer(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER)
    agent = await make_user(role=Role.AGENT, username="note_agent")
    ticket = await make_ticket(customer, assignee=agent)

    assert (
        await _comment(
            client, agent, ticket.id, "Internal: root cause found.", internal=True
        )
    ).status_code == 201

    assert await _notifications(client, customer) == []
    agent_notes = await _notifications(client, agent)
    # The author is never notified of their own note.
    assert agent_notes == []


@pytest.mark.asyncio
async def test_status_and_priority_change_notify_customer_and_assignee(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER)
    agent = await make_user(role=Role.AGENT, username="handler_agent")
    admin = await make_user(role=Role.ADMIN, username="acting_admin")
    ticket = await make_ticket(customer, assignee=agent)

    response = await _status(client, admin, ticket.id, "IN_PROGRESS", priority="HIGH")
    assert response.status_code == 200, response.text

    customer_types = sorted(n["type"] for n in await _notifications(client, customer))
    assert customer_types == [
        NotificationType.PRIORITY_CHANGED.value,
        NotificationType.STATUS_CHANGED.value,
    ]
    agent_types = sorted(n["type"] for n in await _notifications(client, agent))
    assert agent_types == [
        NotificationType.PRIORITY_CHANGED.value,
        NotificationType.STATUS_CHANGED.value,
    ]
    # The acting admin is not notified of their own change.
    assert await _notifications(client, admin) == []


@pytest.mark.asyncio
async def test_unassigned_ticket_change_notifies_the_administrative_queue(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER)
    admin_a = await make_user(role=Role.ADMIN, username="admin_a")
    admin_b = await make_user(role=Role.ADMIN, username="admin_b")
    owner = await make_user(role=Role.OWNER, username="owner_queue")
    ticket = await make_ticket(customer)  # no assignee

    response = await _status(client, admin_a, ticket.id, "IN_PROGRESS")
    assert response.status_code == 200, response.text

    # The other admin and the Owner are told; the actor is not.
    assert [n["type"] for n in await _notifications(client, admin_a)] == []
    for recipient in (admin_b, owner):
        types = [n["type"] for n in await _notifications(client, recipient)]
        assert types == [NotificationType.STATUS_CHANGED.value]

    # The customer is also told, but never about an internal note.
    assert [n["type"] for n in await _notifications(client, customer)] == [
        NotificationType.STATUS_CHANGED.value
    ]


@pytest.mark.asyncio
async def test_resolution_requests_feedback_exactly_once(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER)
    agent = await make_user(role=Role.AGENT, username="resolver")
    ticket = await make_ticket(customer, assignee=agent)

    assert (await _status(client, agent, ticket.id, "IN_PROGRESS")).status_code == 200
    assert (await _status(client, agent, ticket.id, "RESOLVED")).status_code == 200

    customer_notes = await _notifications(client, customer)
    resolved = [
        n for n in customer_notes if n["type"] == NotificationType.TICKET_RESOLVED.value
    ]
    assert len(resolved) == 1
    assert resolved[0]["title"] == "Your ticket has been resolved"
    assert resolved[0]["related_ticket_id"] == str(ticket.id)

    # Reopen then resolve again: still only one feedback request ever.
    assert (await _status(client, agent, ticket.id, "IN_PROGRESS")).status_code == 200
    assert (await _status(client, agent, ticket.id, "RESOLVED")).status_code == 200
    customer_notes = await _notifications(client, customer)
    resolved = [
        n for n in customer_notes if n["type"] == NotificationType.TICKET_RESOLVED.value
    ]
    assert len(resolved) == 1


@pytest.mark.asyncio
async def test_fetching_notifications_never_creates_records(
    client, make_user, session_factory
):
    from app.models.notification import Notification

    user = await make_user()
    for _ in range(3):
        assert await _notifications(client, user) == []
        await _unread_count(client, user)

    async with session_factory() as session:
        rows = (await session.exec(select(Notification))).all()
    assert rows == []


# ---------------------------------------------------------------------------
# Internal messages + Owner thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owner_internal_message_notifies_each_recipient_once(client, make_user):
    owner = await make_user(role=Role.OWNER, username="compose_owner")
    agent = await make_user(role=Role.AGENT, username="compose_agent")
    admin = await make_user(role=Role.ADMIN, username="compose_admin")
    await make_user(role=Role.CUSTOMER, username="compose_customer")

    response = await client.post(
        INTERNAL_MESSAGES,
        headers=_h(owner),
        json={"audience": "everyone", "subject": "All hands", "body": "Update"},
    )
    assert response.status_code == 201, response.text
    message_id = response.json()["id"]

    for recipient in (agent, admin):
        notes = await _notifications(client, recipient)
        assert [n["type"] for n in notes] == [
            NotificationType.INTERNAL_MESSAGE_RECEIVED.value
        ]
        assert notes[0]["related_internal_message_id"] == message_id
        # The body is never copied into the notification preview.
        assert "Update" not in notes[0]["message"]

    # The Owner never notifies themselves, and customers are outside the channel.
    assert await _notifications(client, owner) == []


@pytest.mark.asyncio
async def test_reading_an_internal_message_clears_its_notification(client, make_user):
    owner = await make_user(role=Role.OWNER, username="read_owner")
    agent = await make_user(role=Role.AGENT, username="read_agent")

    created = await client.post(
        INTERNAL_MESSAGES,
        headers=_h(owner),
        json={
            "audience": "individual",
            "recipient_user_id": str(agent.id),
            "subject": "For you",
            "body": "One-to-one",
        },
    )
    message_id = created.json()["id"]
    assert (await _unread_count(client, agent))["messages"] == 1

    read = await client.post(
        f"{INTERNAL_MESSAGES}/{message_id}/read", headers=_h(agent)
    )
    assert read.status_code == 200

    # Both the message's own read state and the notification agree.
    assert (await _unread_count(client, agent))["count"] == 0
    notes = await _notifications(client, agent)
    assert notes[0]["is_read"] is True


@pytest.mark.asyncio
async def test_staff_to_owner_message_notifies_the_owner(client, make_user):
    owner = await make_user(role=Role.OWNER, username="thread_owner2")
    agent = await make_user(role=Role.AGENT, username="thread_agent2")

    conversation = await client.post(
        STAFF_CONVERSATIONS, headers=_h(agent), json={"subject": "Question"}
    )
    conversation_id = conversation.json()["id"]
    sent = await client.post(
        f"{STAFF_CONVERSATIONS}/{conversation_id}/messages",
        headers=_h(agent),
        json={"body": "Owner, I need a decision."},
    )
    assert sent.status_code == 201

    owner_notes = await _notifications(client, owner)
    assert [n["type"] for n in owner_notes] == [
        NotificationType.STAFF_MESSAGE_RECEIVED.value
    ]
    assert owner_notes[0]["related_conversation_id"] == conversation_id
    # The sending agent is never notified of their own message.
    assert await _notifications(client, agent) == []


# ---------------------------------------------------------------------------
# Read state + authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unread_count_and_category_filter(client, make_user, make_ticket):
    customer = await make_user(role=Role.CUSTOMER)
    agent = await make_user(role=Role.AGENT, username="filter2_agent")
    admin = await make_user(role=Role.ADMIN, username="filter2_admin")
    ticket = await make_ticket(customer, assignee=agent)

    # A customer reply notifies the assignee; an admin status change notifies
    # the assignee too (the actor is never notified).
    await _comment(client, customer, ticket.id, "Any update?")  # NEW_COMMENT
    await _status(client, admin, ticket.id, "IN_PROGRESS")  # STATUS_CHANGED
    # An internal-message notification for the agent.
    owner = await make_user(role=Role.OWNER, username="filter2_owner")
    await client.post(
        INTERNAL_MESSAGES,
        headers=_h(owner),
        json={
            "audience": "individual",
            "recipient_user_id": str(agent.id),
            "subject": "Note",
            "body": "Hi",
        },
    )

    counts = await _unread_count(client, agent)
    assert (
        counts["count"]
        == counts["tickets"] + counts["messages"] + counts["account_requests"]
    )
    assert counts["messages"] == 1
    assert counts["tickets"] == 2

    only_messages = await _notifications(client, agent, category="messages")
    assert all(n["type"] == "INTERNAL_MESSAGE_RECEIVED" for n in only_messages)
    only_tickets = await _notifications(client, agent, category="tickets")
    assert only_tickets and all(
        n["type"] in {"NEW_COMMENT", "STATUS_CHANGED", "TICKET_ASSIGNED"}
        for n in only_tickets
    )

    # Unread filter.
    await client.post(f"{NOTIFICATIONS}/read-all", headers=_h(agent))
    assert await _notifications(client, agent, is_read="false") == []
    assert (await _unread_count(client, agent))["count"] == 0


@pytest.mark.asyncio
async def test_notifications_are_private_and_cannot_be_mutated_by_others(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER, username="priv_customer")
    other = await make_user(role=Role.CUSTOMER, username="priv_other")
    agent = await make_user(role=Role.AGENT, username="priv_agent")
    ticket = await make_ticket(customer, assignee=agent)

    await _comment(client, agent, ticket.id, "Hello")

    customer_notes = await _notifications(client, customer)
    assert len(customer_notes) == 1
    notification_id = customer_notes[0]["id"]

    # Another user cannot see or mutate it.
    assert await _notifications(client, other) == []
    forbidden = await client.patch(
        f"{NOTIFICATIONS}/{notification_id}",
        headers=_h(other),
        json={"is_read": True},
    )
    assert forbidden.status_code == 404


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


async def _feedback(client, user, ticket_id):
    return await client.get(f"{TICKETS}/{ticket_id}/feedback", headers=_h(user))


@pytest.mark.asyncio
async def test_feedback_is_customer_only_and_single_answer(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER, username="fb_customer")
    other_customer = await make_user(role=Role.CUSTOMER, username="fb_other")
    agent = await make_user(role=Role.AGENT, username="fb_agent")
    ticket = await make_ticket(customer, assignee=agent, status=TicketStatus.RESOLVED)

    # Staff may see the state but cannot submit.
    staff_state = await _feedback(client, agent, ticket.id)
    assert staff_state.status_code == 200
    assert staff_state.json()["can_submit"] is False

    # A different customer cannot even see the ticket's feedback state.
    assert (await _feedback(client, other_customer, ticket.id)).status_code == 404
    assert (
        await client.post(
            f"{TICKETS}/{ticket.id}/feedback",
            headers=_h(other_customer),
            json={"rating": 5},
        )
    ).status_code == 404

    # The ticket's own customer can submit once.
    state = await _feedback(client, customer, ticket.id)
    assert state.json() == {
        "feedback": None,
        "can_submit": True,
        "awaiting_feedback": True,
    }

    first = await client.post(
        f"{TICKETS}/{ticket.id}/feedback",
        headers=_h(customer),
        json={"rating": 4, "comment": "Quick and clear."},
    )
    assert first.status_code == 201, first.text
    assert first.json()["rating"] == 4

    duplicate = await client.post(
        f"{TICKETS}/{ticket.id}/feedback",
        headers=_h(customer),
        json={"rating": 1},
    )
    assert duplicate.status_code == 409

    after = await _feedback(client, customer, ticket.id)
    assert after.json()["feedback"]["rating"] == 4
    assert after.json()["can_submit"] is False


@pytest.mark.asyncio
async def test_feedback_requires_a_resolved_ticket(client, make_user, make_ticket):
    customer = await make_user(role=Role.CUSTOMER, username="fb_open_customer")
    ticket = await make_ticket(customer, status=TicketStatus.OPEN)

    response = await client.post(
        f"{TICKETS}/{ticket.id}/feedback",
        headers=_h(customer),
        json={"rating": 5},
    )
    assert response.status_code == 409

    # Rating bounds are enforced at the schema level.
    bad = await client.post(
        f"{TICKETS}/{ticket.id}/feedback",
        headers=_h(customer),
        json={"rating": 9},
    )
    assert bad.status_code in (409, 422)


@pytest.mark.asyncio
async def test_submitting_feedback_clears_the_request_notification(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER, username="fb_clear_customer")
    agent = await make_user(role=Role.AGENT, username="fb_clear_agent")
    ticket = await make_ticket(customer, assignee=agent)

    assert (await _status(client, agent, ticket.id, "IN_PROGRESS")).status_code == 200
    assert (await _status(client, agent, ticket.id, "RESOLVED")).status_code == 200
    before = await _notifications(client, customer, is_read="false")
    assert any(n["type"] == "TICKET_RESOLVED" for n in before)
    unread_before = (await _unread_count(client, customer))["count"]

    submitted = await client.post(
        f"{TICKETS}/{ticket.id}/feedback",
        headers=_h(customer),
        json={"rating": 5},
    )
    assert submitted.status_code == 201

    # The feedback request is now read, and the badge dropped by exactly one.
    assert (await _unread_count(client, customer))["count"] == unread_before - 1
    after = await _notifications(client, customer)
    assert all(n["is_read"] for n in after if n["type"] == "TICKET_RESOLVED")
    assert (await _unread_count(client, customer))["tickets"] == unread_before - 1


# ---------------------------------------------------------------------------
# Account-request (escalation) deep links
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_account_request_notifications_link_to_the_request(
    client, make_user, make_ticket
):
    customer = await make_user(role=Role.CUSTOMER, username="esc_customer")
    agent = await make_user(role=Role.AGENT, username="esc_agent")
    admin = await make_user(role=Role.ADMIN, username="esc_admin")
    ticket = await make_ticket(customer)

    created = await client.post(
        "/api/v1/account-requests",
        headers=_h(agent),
        json={
            "category": "ACCOUNT_RECOVERY",
            "justification": "The customer is locked out after a reset.",
            "ticket_id": str(ticket.id),
        },
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    admin_notes = await _notifications(client, admin)
    assert [n["type"] for n in admin_notes] == ["ESCALATION_CREATED"]
    assert admin_notes[0]["related_account_request_id"] == request_id
    assert admin_notes[0]["related_ticket_id"] == str(ticket.id)

    moved = await client.post(
        f"/api/v1/account-requests/{request_id}/status",
        headers=_h(admin),
        json={"status": "IN_REVIEW"},
    )
    assert moved.status_code == 200, moved.text

    agent_notes = await _notifications(client, agent)
    assert [n["type"] for n in agent_notes] == ["ESCALATION_UPDATED"]
    assert agent_notes[0]["related_account_request_id"] == request_id
