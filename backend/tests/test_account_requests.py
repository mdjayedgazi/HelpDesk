"""Account-management (admin escalation) request workflow.

Pins the rules:

* only AGENT/ADMIN may open a request; the Owner reviews, customers are
  denied entirely;
* an agent's target always comes from a ticket they can see (trusted records),
  never from an arbitrary client id;
* the lifecycle is ``PENDING -> IN_REVIEW -> APPROVED/REJECTED`` and
  ``APPROVED -> COMPLETED``, with an append-only audit trail;
* the creator can never decide their own request; rejections need a reason;
* nothing in the API can mutate an identity (no clerk id / email / role
  fields are accepted anywhere).
"""

import uuid
from uuid import UUID

import pytest
from sqlmodel import select

from app.enums.enums import (
    EscalationCategory,
    EscalationStatus,
    NotificationType,
    Role,
)
from app.models.account_request import AccountManagementRequest
from app.models.notification import Notification

BASE = "/api/v1/account-requests"


async def _create(client, user, **overrides):
    payload = {
        "category": "ACCOUNT_RECOVERY",
        "justification": "The customer is locked out after a password reset.",
    }
    payload.update(overrides)
    return await client.post(BASE, headers={"X-Test-User": user.username}, json=payload)


async def _status(client, user, request_id, status, reason=None):
    payload = {"status": status}
    if reason is not None:
        payload["reason"] = reason
    return await client.post(
        f"{BASE}/{request_id}/status",
        headers={"X-Test-User": user.username},
        json=payload,
    )


async def _comment(client, user, request_id, body):
    return await client.post(
        f"{BASE}/{request_id}/comments",
        headers={"X-Test-User": user.username},
        json={"body": body},
    )


@pytest.mark.asyncio
async def test_customer_is_denied_everywhere(client, make_user, make_ticket):
    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    await make_user(role=Role.ADMIN)
    ticket = await make_ticket(customer)

    created = await _create(client, agent, ticket_id=str(ticket.id))
    assert created.status_code == 201
    request_id = created.json()["id"]

    headers = {"X-Test-User": customer.username}
    assert (await client.get(BASE, headers=headers)).status_code == 403
    assert (
        await _create(client, customer, ticket_id=str(ticket.id))
    ).status_code == 403
    assert (
        await client.get(f"{BASE}/{request_id}", headers=headers)
    ).status_code == 403
    assert (
        await _comment(client, customer, request_id, "let me in")
    ).status_code == 403
    assert (await _status(client, customer, request_id, "APPROVED")).status_code == 403


@pytest.mark.asyncio
async def test_owner_cannot_create_requests(client, make_user, make_ticket):
    owner = await make_user(role=Role.OWNER)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await _create(client, owner, ticket_id=str(ticket.id))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_request_target_comes_from_the_ticket(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await _create(
        client,
        agent,
        ticket_id=str(ticket.id),
        category="PROFILE_CORRECTION",
        internal_details="Verified over the registered phone number.",
    )
    assert response.status_code == 201

    body = response.json()
    assert body["target_user_id"] == str(customer.id)
    assert body["target_full_name_snapshot"] == customer.full_name
    assert body["target_email_snapshot"] == customer.email
    assert body["ticket_id"] == str(ticket.id)
    assert body["status"] == "PENDING"
    assert body["created_by_user_id"] == str(agent.id)
    assert body["decided_by_user_id"] is None
    assert body["decided_at"] is None
    assert body["completed_at"] is None


@pytest.mark.asyncio
async def test_agent_cannot_choose_an_arbitrary_target(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    victim = await make_user()
    customer = await make_user()
    ticket = await make_ticket(customer)

    mismatch = await _create(
        client, agent, ticket_id=str(ticket.id), target_user_id=str(victim.id)
    )
    assert mismatch.status_code == 422

    # Repeating the real requester id is allowed.
    same = await _create(
        client, agent, ticket_id=str(ticket.id), target_user_id=str(customer.id)
    )
    assert same.status_code == 201


@pytest.mark.asyncio
async def test_agent_request_requires_a_visible_ticket(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    foreign_ticket = await make_ticket(customer, assignee=other_agent)

    no_ticket = await _create(client, agent, target_user_id=str(customer.id))
    assert no_ticket.status_code == 422

    # An agent cannot escalate about a ticket outside their visibility.
    forbidden = await _create(client, agent, ticket_id=str(foreign_ticket.id))
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_target_a_directory_user(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    target = await make_user()

    response = await _create(
        client,
        admin,
        target_user_id=str(target.id),
        category="IDENTITY_LINKING",
    )
    assert response.status_code == 201
    assert response.json()["target_user_id"] == str(target.id)
    assert response.json()["ticket_id"] is None


@pytest.mark.asyncio
async def test_admin_needs_a_ticket_or_a_target(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    response = await _create(client, admin)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_owner_cannot_be_a_target(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    owner = await make_user(role=Role.OWNER)

    response = await _create(client, admin, target_user_id=str(owner.id))
    assert response.status_code == 422
    assert "Owner" in response.json()["detail"]


@pytest.mark.asyncio
async def test_identity_fields_are_rejected(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    for extra in (
        {"clerk_id": "user_hijack"},
        {"email": "attacker@example.com"},
        {"role": "OWNER"},
        {"target_user_id": str(customer.id), "new_clerk_id": "x"},
    ):
        response = await _create(client, admin, ticket_id=str(ticket.id), **extra)
        assert response.status_code == 422, extra


@pytest.mark.asyncio
async def test_visibility_is_creator_or_admin(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    creator = await make_user(role=Role.AGENT)
    other = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    created = await _create(client, creator, ticket_id=str(ticket.id))
    request_id = created.json()["id"]

    mine = await client.get(
        f"{BASE}/{request_id}", headers={"X-Test-User": creator.username}
    )
    assert mine.status_code == 200

    admin_view = await client.get(
        f"{BASE}/{request_id}", headers={"X-Test-User": admin.username}
    )
    assert admin_view.status_code == 200

    stranger = await client.get(
        f"{BASE}/{request_id}", headers={"X-Test-User": other.username}
    )
    assert stranger.status_code == 404

    # The agent list only ever contains their own requests.
    other_created = await _create(client, other, ticket_id=str(ticket.id))
    assert other_created.status_code == 201

    creator_list = await client.get(BASE, headers={"X-Test-User": creator.username})
    assert [r["id"] for r in creator_list.json()] == [request_id]

    admin_list = await client.get(BASE, headers={"X-Test-User": admin.username})
    assert {r["id"] for r in admin_list.json()} == {
        request_id,
        other_created.json()["id"],
    }

    filtered = await client.get(
        BASE,
        headers={"X-Test-User": admin.username},
        params={"status": "PENDING"},
    )
    assert {r["id"] for r in filtered.json()} == {
        request_id,
        other_created.json()["id"],
    }


@pytest.mark.asyncio
async def test_decision_lifecycle_and_audit(
    client, make_user, make_ticket, session_factory
):
    admin = await make_user(role=Role.ADMIN)
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)
    request_id = (await _create(client, agent, ticket_id=str(ticket.id))).json()["id"]

    # Invalid jumps are rejected.
    assert (await _status(client, admin, request_id, "COMPLETED")).status_code == 409

    # Start the review, then approve.
    in_review = await _status(client, admin, request_id, "IN_REVIEW")
    assert in_review.status_code == 200
    assert in_review.json()["status"] == "IN_REVIEW"

    approved = await _status(
        client, owner, request_id, "APPROVED", reason="Verified with the customer."
    )
    assert approved.status_code == 200
    approved_body = approved.json()
    assert approved_body["status"] == "APPROVED"
    assert approved_body["decided_by_user_id"] == str(owner.id)
    assert approved_body["decided_at"] is not None
    assert approved_body["decision_reason"] == "Verified with the customer."

    # A decided request can no longer jump back.
    assert (await _status(client, admin, request_id, "IN_REVIEW")).status_code == 409

    completed = await _status(
        client, admin, request_id, "COMPLETED", reason="Changed via Clerk."
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["completed_by_user_id"] == str(admin.id)
    assert completed.json()["completed_at"] is not None

    # The full audit trail is visible in the detail response.
    detail = await client.get(
        f"{BASE}/{request_id}", headers={"X-Test-User": admin.username}
    )
    events = detail.json()["events"]
    assert [e["event_type"] for e in events] == [
        "REQUEST_CREATED",
        "STATUS_CHANGED",
        "STATUS_CHANGED",
        "STATUS_CHANGED",
    ]
    assert events[0]["new_value"]["status"] == "PENDING"
    assert events[-1]["new_value"]["status"] == "COMPLETED"

    # The creator was notified about each decision, never the actor.
    async with session_factory() as session:
        notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == agent.id,
                    Notification.type == NotificationType.ESCALATION_UPDATED,
                )
            )
        ).all()
    assert len(notifications) == 3  # IN_REVIEW, APPROVED, COMPLETED


@pytest.mark.asyncio
async def test_rejection_requires_a_reason(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)
    request_id = (await _create(client, agent, ticket_id=str(ticket.id))).json()["id"]

    missing = await _status(client, admin, request_id, "REJECTED")
    assert missing.status_code == 422

    blank = await _status(client, admin, request_id, "REJECTED", reason="   ")
    assert blank.status_code == 422

    rejected = await _status(
        client, admin, request_id, "REJECTED", reason="Policy does not allow this."
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["decision_reason"] == "Policy does not allow this."

    # REJECTED is terminal.
    assert (await _status(client, admin, request_id, "APPROVED")).status_code == 409
    assert (await _comment(client, admin, request_id, "reopen?")).status_code == 409


@pytest.mark.asyncio
async def test_agent_cannot_decide_or_review(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)
    request_id = (await _create(client, agent, ticket_id=str(ticket.id))).json()["id"]

    response = await _status(client, agent, request_id, "APPROVED")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_creator_cannot_decide_own_request(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    other_admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    request_id = (
        await _create(
            client,
            admin,
            ticket_id=str(ticket.id),
            category="ROLE_OR_STATUS_CHANGE",
        )
    ).json()["id"]

    own = await _status(client, admin, request_id, "APPROVED")
    assert own.status_code == 403
    assert "own request" in own.json()["detail"]

    # Another authorized reviewer can decide it.
    other = await _status(client, other_admin, request_id, "APPROVED")
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_comments_notify_the_other_side(
    client, make_user, make_ticket, session_factory
):
    admin = await make_user(role=Role.ADMIN)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)
    request_id = (await _create(client, agent, ticket_id=str(ticket.id))).json()["id"]

    # Reviewer comment -> creator notified.
    reviewer_comment = await _comment(
        client, admin, request_id, "Can you confirm the verification method?"
    )
    assert reviewer_comment.status_code == 201

    # Creator comment -> reviewers notified (except the creator).
    creator_comment = await _comment(
        client, agent, request_id, "Confirmed against the registered phone."
    )
    assert creator_comment.status_code == 201

    async with session_factory() as session:
        creator_notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == agent.id,
                    Notification.type == NotificationType.ESCALATION_UPDATED,
                )
            )
        ).all()
    assert len(creator_notifications) == 1

    detail = await client.get(
        f"{BASE}/{request_id}", headers={"X-Test-User": admin.username}
    )
    bodies = [c["body"] for c in detail.json()["comments"]]
    assert bodies == [
        "Can you confirm the verification method?",
        "Confirmed against the registered phone.",
    ]


@pytest.mark.asyncio
async def test_unknown_request_returns_404(client, make_user):

    admin = await make_user(role=Role.ADMIN)
    response = await client.get(
        f"{BASE}/{uuid.uuid4()}", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stored_state_matches_the_api(
    client, make_user, make_ticket, session_factory
):
    await make_user(role=Role.ADMIN)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    created = await _create(
        client,
        agent,
        ticket_id=str(ticket.id),
        category="ACCOUNT_RECOVERY",
        justification="Locked out.",
        internal_details="Internal note.",
    )
    request_id = created.json()["id"]

    async with session_factory() as session:
        stored = await session.get(AccountManagementRequest, UUID(request_id))
    assert stored is not None
    assert stored.category == EscalationCategory.ACCOUNT_RECOVERY
    assert stored.status == EscalationStatus.PENDING
    assert stored.target_email_snapshot == customer.email
