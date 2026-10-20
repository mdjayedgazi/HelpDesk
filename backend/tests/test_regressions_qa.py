"""Additional regression tests added during the QA pass.

These deliberately probe authorization, notification, assignment and
validation behaviour that the original suite did not cover. They run against
the in-memory SQLite database with the real routers and the shared
``X-Test-User`` Clerk stub, exactly like the rest of the suite.
"""

import uuid

import pytest
from sqlmodel import select

from app.enums.enums import NotificationType, Role, TicketPriority, TicketStatus
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory


async def _history_events(session_factory, ticket_id) -> list[TicketHistory]:
    async with session_factory() as session:
        result = await session.exec(
            select(TicketHistory).where(TicketHistory.ticket_id == ticket_id)
        )
        return list(result.all())


async def _notifications(session_factory, recipient_id):
    async with session_factory() as session:
        result = await session.exec(
            select(Notification).where(Notification.recipient_user_id == recipient_id)
        )
        return list(result.all())


# --------------------------------------------------------------------------- #
# Assignment lifecycle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_owner_can_assign_and_unassign_ticket(
    client, make_user, make_ticket, session_factory
):
    owner = await make_user(role=Role.OWNER)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    assign = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": owner.username},
        json={"assignee_user_id": str(agent.id)},
    )
    assert assign.status_code == 200
    assert assign.json()["assignee_user_id"] == str(agent.id)

    unassign = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": owner.username},
        json={"assignee_user_id": None},
    )
    assert unassign.status_code == 200
    assert unassign.json()["assignee_user_id"] is None

    events = [e.event_type for e in await _history_events(session_factory, ticket.id)]
    assert events.count("TICKET_ASSIGNED") == 2

    # Assigning the ticket notified the agent; unassigning notified nobody else.
    agent_notices = await _notifications(session_factory, agent.id)
    assert any(n.type == NotificationType.TICKET_ASSIGNED for n in agent_notices)


@pytest.mark.asyncio
async def test_assign_unknown_user_is_404(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_claiming_own_assigned_ticket_conflicts(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/claim",
        headers={"X-Test-User": agent.username},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_claiming_another_agents_ticket_is_hidden(client, make_user, make_ticket):
    agent = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=other_agent)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/claim",
        headers={"X-Test-User": agent.username},
    )
    # The ticket is not visible to this agent, so it does not exist for them.
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Ticket update validation and notifications
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_staff_update_rejects_client_supplied_system_fields(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"created_by_user_id": str(agent.id)},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_customer_cannot_change_priority(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": customer.username},
        json={"priority": "URGENT"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_priority_change_notifies_customer(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"priority": "URGENT"},
    )
    assert response.status_code == 200
    assert response.json()["priority"] == "URGENT"

    notices = await _notifications(session_factory, customer.id)
    assert any(n.type == NotificationType.PRIORITY_CHANGED for n in notices)


@pytest.mark.asyncio
async def test_resolved_at_is_set_and_cleared_on_reopen(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(
        customer, assignee=agent, status=TicketStatus.IN_PROGRESS
    )

    resolved = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"status": "RESOLVED"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved_at"] is not None

    reopened = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"status": "IN_PROGRESS"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None


@pytest.mark.asyncio
async def test_staff_description_edit_records_history(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"description": "Updated by support with new findings."},
    )
    assert response.status_code == 200

    events = [e.event_type for e in await _history_events(session_factory, ticket.id)]
    assert "TICKET_UPDATED" in events


# --------------------------------------------------------------------------- #
# Comments and notifications
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_public_staff_comment_notifies_customer(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": agent.username},
        json={"body": "We have started working on this."},
    )
    assert response.status_code == 201

    notices = await _notifications(session_factory, customer.id)
    assert any(n.type == NotificationType.NEW_COMMENT for n in notices)


@pytest.mark.asyncio
async def test_internal_note_does_not_notify_customer_or_write_history(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": agent.username},
        json={"body": "Internal: escalate to tier 2.", "is_internal": True},
    )
    assert response.status_code == 201

    assert await _notifications(session_factory, customer.id) == []
    events = [e.event_type for e in await _history_events(session_factory, ticket.id)]
    assert "COMMENT_ADDED" not in events


@pytest.mark.asyncio
async def test_admin_can_create_internal_note(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": admin.username},
        json={"body": "Internal admin note.", "is_internal": True},
    )
    assert response.status_code == 201
    assert response.json()["is_internal"] is True


# --------------------------------------------------------------------------- #
# Attachments
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_list_attachments_of_foreign_ticket_is_404(
    client, make_user, make_ticket
):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": alice.username},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_download_attachment_on_any_ticket(
    client, make_user, make_ticket
):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    upload = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"staff can read this", "text/plain")},
    )
    assert upload.status_code == 201

    download = await client.get(
        f"/api/v1/attachments/{upload.json()['id']}/download",
        headers={"X-Test-User": admin.username},
    )
    assert download.status_code == 200
    assert download.content == b"staff can read this"


@pytest.mark.asyncio
async def test_png_upload_is_accepted(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000d4944415478da63fcffff3f030005000101a5f645"
        "0000000049454e44ae426082"
    )

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("dot.png", png, "image/png")},
    )
    assert response.status_code == 201
    assert response.json()["content_type"] == "image/png"


# --------------------------------------------------------------------------- #
# User management
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_owner_can_update_another_users_profile(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers={"X-Test-User": owner.username},
        json={"full_name": "Renamed By Owner"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed By Owner"


@pytest.mark.asyncio
async def test_owner_cannot_change_own_role_via_generic_endpoint(client, make_user):
    owner = await make_user(role=Role.OWNER)

    response = await client.patch(
        f"/api/v1/users/{owner.id}",
        headers={"X-Test-User": owner.username},
        json={"role": "customer"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_directory_search_and_pagination(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    await make_user(username="findmeone", email="findmeone@example.test")
    await make_user(username="findmetwo", email="findmetwo@example.test")

    found = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"q": "findme"},
    )
    assert found.status_code == 200
    assert len(found.json()) == 2

    page = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"limit": 1},
    )
    assert page.status_code == 200
    assert len(page.json()) == 1


@pytest.mark.asyncio
async def test_me_update_rejects_account_status(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"is_active": False},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reserved_test_domain_email_is_serialized(client, make_user):
    """Regression: a stored reserved-domain email must not become an HTTP 500.

    ``UserRead.email`` used pydantic's ``EmailStr``, which rejects the reserved
    ``.test`` domain during *response* validation, so listing or reading any user
    with a QA/staging address failed with an unhandled 500.
    """
    user = await make_user(username="qa_reserved", email="qa.reserved@example.test")

    me = await client.get("/api/v1/users/me", headers={"X-Test-User": user.username})
    assert me.status_code == 200
    assert me.json()["email"] == "qa.reserved@example.test"

    admin = await make_user(role=Role.ADMIN)
    listing = await client.get("/api/v1/users", headers={"X-Test-User": admin.username})
    assert listing.status_code == 200
    assert any(u["email"] == "qa.reserved@example.test" for u in listing.json())


@pytest.mark.asyncio
async def test_profile_update_accepts_reserved_domain(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"email": "new.address@example.test"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "new.address@example.test"


@pytest.mark.asyncio
async def test_invalid_email_is_still_rejected(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"email": "not-an-email"},
    )
    # Syntax validation is preserved even though reserved domains are allowed.
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_owner_cannot_deactivate_the_owner_account(client, make_user):
    owner = await make_user(role=Role.OWNER)
    response = await client.patch(
        f"/api/v1/users/{owner.id}/status",
        headers={"X-Test-User": owner.username},
        json={"is_active": False},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Cross-role authorization matrix
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.CUSTOMER, 403),
        (Role.AGENT, 403),
        (Role.ADMIN, 200),
        (Role.OWNER, 200),
    ],
)
async def test_dashboard_matrix(client, make_user, role, expected):
    user = await make_user(role=role)
    response = await client.get(
        "/api/v1/admin/dashboard", headers={"X-Test-User": user.username}
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.CUSTOMER, 403),
        (Role.AGENT, 403),
        (Role.ADMIN, 200),
        (Role.OWNER, 200),
    ],
)
async def test_user_directory_matrix(client, make_user, role, expected):
    user = await make_user(role=role)
    response = await client.get("/api/v1/users", headers={"X-Test-User": user.username})
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.CUSTOMER, 403),
        (Role.AGENT, 200),
        (Role.ADMIN, 403),
        (Role.OWNER, 403),
    ],
)
async def test_agent_queue_is_agent_only(client, make_user, role, expected):
    user = await make_user(role=role)
    response = await client.get(
        "/api/v1/tickets/assigned", headers={"X-Test-User": user.username}
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.CUSTOMER, 403),
        (Role.AGENT, 403),
        (Role.ADMIN, 200),
        (Role.OWNER, 200),
    ],
)
async def test_assign_endpoint_matrix(client, make_user, make_ticket, role, expected):
    actor = await make_user(role=role)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": actor.username},
        json={"assignee_user_id": str(agent.id)},
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.CUSTOMER, 201),
        (Role.AGENT, 403),
        (Role.ADMIN, 403),
        (Role.OWNER, 403),
    ],
)
async def test_ticket_create_matrix(client, make_user, role, expected):
    user = await make_user(role=role)
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": user.username},
        json={
            "title": "Matrix ticket",
            "description": "Created by the matrix test.",
            "category": "OTHER",
        },
    )
    assert response.status_code == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.CUSTOMER, 403),
        (Role.AGENT, 200),
        (Role.ADMIN, 200),
        (Role.OWNER, 200),
    ],
)
async def test_ticket_history_matrix(client, make_user, make_ticket, role, expected):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    # Assign to the acting agent when the actor is an agent, else to another
    # agent so admins/owners still see the ticket and the role check is isolated.
    ticket = await make_ticket(customer, assignee=agent)

    actor = agent if role == Role.AGENT else await make_user(role=role)
    response = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": actor.username},
    )
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_ticket_number_allocated_after_max(client, make_user, make_ticket):
    customer = await make_user()
    first = await make_ticket(customer)

    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Next number",
            "description": "Should follow the max.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 201
    assert response.json()["ticket_number"] == first.ticket_number + 1


@pytest.mark.asyncio
async def test_priority_filter_and_search(client, make_user, make_ticket):
    customer = await make_user()
    await make_ticket(customer, title="Alpha urgent", priority=TicketPriority.URGENT)
    await make_ticket(customer, title="Beta low", priority=TicketPriority.LOW)

    urgent = await client.get(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        params={"priority": "URGENT"},
    )
    assert urgent.status_code == 200
    assert {t["title"] for t in urgent.json()} == {"Alpha urgent"}

    searched = await client.get(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        params={"q": "beta"},
    )
    assert searched.status_code == 200
    assert {t["title"] for t in searched.json()} == {"Beta low"}


@pytest.mark.asyncio
async def test_agent_only_sees_visible_tickets_in_own_queue(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    unassigned = await make_ticket(customer)
    assigned = await make_ticket(customer, assignee=agent)

    response = await client.get(
        "/api/v1/tickets/assigned", headers={"X-Test-User": agent.username}
    )
    ids = {t["id"] for t in response.json()}
    assert str(assigned.id) in ids
    assert str(unassigned.id) not in ids

    async with session_factory() as session:
        stored = await session.get(Ticket, assigned.id)
        assert stored is not None
