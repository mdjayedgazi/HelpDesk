import uuid

import pytest
from fastapi import HTTPException

from app.enums.enums import Role
from app.models.user import User


@pytest.mark.asyncio
async def test_customer_cannot_access_admin_dashboard(client, make_user):
    customer = await make_user()
    response = await client.get(
        "/api/v1/admin/dashboard", headers={"X-Test-User": customer.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_list_users(client, make_user):
    customer = await make_user()
    response = await client.get(
        "/api/v1/users", headers={"X-Test-User": customer.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_dashboard_counts(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    await make_ticket(customer)
    await make_ticket(customer)

    response = await client.get(
        "/api/v1/admin/dashboard", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_tickets"] == 2
    assert body["tickets_by_status"]["OPEN"] == 2
    assert body["total_users"] >= 2


@pytest.mark.asyncio
async def test_admin_lists_and_filters_users(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    await make_user(role=Role.AGENT)

    response = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"role": "agent"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["role"] == "agent"
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["total_pages"] == 1
    assert body["has_next"] is False
    assert body["has_previous"] is False


@pytest.mark.asyncio
async def test_admin_lists_assignable_agents(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    await make_user(role=Role.AGENT)
    await make_user(role=Role.ADMIN, is_active=False)

    response = await client.get(
        "/api/v1/admin/agents", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["role"] == "agent"


@pytest.mark.asyncio
async def test_admin_cannot_change_user_role(client, make_user):
    """User management is Owner-only: an ordinary admin is forbidden."""
    admin = await make_user(role=Role.ADMIN)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": admin.username},
        json={"role": "agent"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_customer_cannot_change_role(client, make_user):
    customer = await make_user()
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": customer.username},
        json={"role": "admin"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_change_user_status(client, make_user):
    """Account activation is Owner-only as well."""
    admin = await make_user(role=Role.ADMIN)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}/status",
        headers={"X-Test-User": admin.username},
        json={"is_active": False},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_update_other_profile(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers={"X-Test-User": admin.username},
        json={"full_name": "Renamed By Admin"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_assign_ticket(client, make_user, make_ticket):
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


@pytest.mark.asyncio
async def test_assignment_to_customer_rejected(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    other_customer = await make_user(role=Role.CUSTOMER)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": str(other_customer.id)},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assignment_to_admin_rejected(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    other_admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": str(other_admin.id)},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_assignment_to_inactive_agent_rejected(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    inactive_agent = await make_user(role=Role.AGENT, is_active=False)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": str(inactive_agent.id)},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_any_account(client, make_user):
    """Admins keep ticket/dashboard tools but no account management."""
    admin = await make_user(role=Role.ADMIN)

    response = await client.patch(
        f"/api/v1/users/{admin.id}/status",
        headers={"X-Test-User": admin.username},
        json={"is_active": False},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_still_list_users(client, make_user):
    """Reading the directory stays available to admins (display-name lookup)."""
    admin = await make_user(role=Role.ADMIN)
    await make_user()

    response = await client.get(
        "/api/v1/users", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_last_active_admin_cannot_be_removed(client, make_user, session_factory):
    """The final active administrative account is protected from removal."""
    from app.api.routers.users import _guard_managed_user_change

    only_admin = await make_user(role=Role.ADMIN)

    # An acting admin that is not the target. This isolates the
    # "last administrative account" rule from the self-protection rule.
    actor = User(
        full_name="Acting Admin",
        username=f"actor_{uuid.uuid4().hex[:8]}",
        email=f"actor_{uuid.uuid4().hex[:8]}@example.com",
        role=Role.ADMIN,
        is_active=True,
    )

    async with session_factory() as session:
        with pytest.raises(HTTPException) as excinfo:
            await _guard_managed_user_change(
                session, actor, only_admin, {"is_active": False}
            )

    assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# User directory pagination (server-side envelope)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_page_envelope_shape_and_empty_database(client, make_user):
    """The directory returns a typed envelope; an admin may be the only row."""
    admin = await make_user(role=Role.ADMIN)
    response = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"q": "no-such-user-anywhere"},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "items",
        "total",
        "page",
        "page_size",
        "total_pages",
        "has_next",
        "has_previous",
    }
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["total_pages"] == 1
    assert body["has_next"] is False
    assert body["has_previous"] is False


@pytest.mark.asyncio
async def test_user_page_exact_full_page_has_no_next(client, make_user):
    """An exactly-full single page reports has_next False and truthy total."""
    admin = await make_user(role=Role.ADMIN)
    for _ in range(3):
        await make_user(username=f"full_{uuid.uuid4().hex[:8]}")

    response = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"page": 1, "page_size": 4},
    )
    body = response.json()
    assert body["total"] == 4
    assert len(body["items"]) == 4
    assert body["total_pages"] == 1
    assert body["has_next"] is False
    assert body["has_previous"] is False


@pytest.mark.asyncio
async def test_user_page_multiple_pages_deterministic_order(client, make_user):
    """Pages partition the set with no duplicates or omissions, stably ordered."""
    admin = await make_user(role=Role.ADMIN)
    for _ in range(5):
        await make_user(username=f"multi_{uuid.uuid4().hex[:8]}")

    seen: list[str] = []
    page = 1
    while True:
        response = await client.get(
            "/api/v1/users",
            headers={"X-Test-User": admin.username},
            params={"page": page, "page_size": 2},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 6
        assert body["total_pages"] == 3
        seen.extend(u["id"] for u in body["items"])
        assert body["has_previous"] is (page > 1)
        if not body["has_next"]:
            break
        page += 1
    assert page == 3
    assert len(seen) == 6
    assert len(set(seen)) == 6

    # Re-fetching the same pages yields the same order (deterministic).
    first_again = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"page": 1, "page_size": 2},
    )
    assert [u["id"] for u in first_again.json()["items"]] == seen[:2]


@pytest.mark.asyncio
async def test_user_page_partial_last_page(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    for _ in range(2):
        await make_user(username=f"part_{uuid.uuid4().hex[:8]}")

    response = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"page": 2, "page_size": 2},
    )
    body = response.json()
    assert body["total"] == 3
    assert body["total_pages"] == 2
    assert len(body["items"]) == 1
    assert body["has_previous"] is True
    assert body["has_next"] is False


@pytest.mark.asyncio
async def test_user_page_out_of_range_returns_true_total(client, make_user):
    """A deep out-of-range page returns no items but the real total/pages."""
    admin = await make_user(role=Role.ADMIN)
    await make_user(username=f"oor_{uuid.uuid4().hex[:8]}")

    response = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"page": 99, "page_size": 2},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["items"] == []
    assert body["total"] == 2
    assert body["total_pages"] == 1
    assert body["page"] == 99
    assert body["has_next"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}],
)
async def test_user_page_rejects_invalid_bounds(client, make_user, params):
    admin = await make_user(role=Role.ADMIN)
    response = await client.get(
        "/api/v1/users", headers={"X-Test-User": admin.username}, params=params
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_user_page_max_page_size(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    response = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"page_size": 100},
    )
    assert response.status_code == 200
    assert response.json()["page_size"] == 100


@pytest.mark.asyncio
async def test_user_page_filters_reflected_in_total(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    await make_user(role=Role.AGENT, is_active=False)
    await make_user(role=Role.AGENT)

    active_agents = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"role": "agent", "is_active": True},
    )
    body = active_agents.json()
    assert body["total"] == 1
    assert all(u["role"] == "agent" and u["is_active"] for u in body["items"])

    inactive = await client.get(
        "/api/v1/users",
        headers={"X-Test-User": admin.username},
        params={"is_active": False},
    )
    assert inactive.json()["total"] == 1
    assert inactive.json()["items"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_user_page_requires_admin_or_owner(client, make_user):
    for role in (Role.CUSTOMER, Role.AGENT):
        user = await make_user(role=role)
        response = await client.get(
            "/api/v1/users", headers={"X-Test-User": user.username}
        )
        assert response.status_code == 403
