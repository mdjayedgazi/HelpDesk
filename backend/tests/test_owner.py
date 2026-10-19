"""Owner-only user-management authorization tests.

Everything runs against the real routers and the real ``get_current_user``
dependency with Clerk mocked by the shared ``X-Test-User`` header, so no
PostgreSQL or Clerk credentials are required.
"""

import uuid

import pytest
from sqlmodel import select

from app.enums.enums import AssignableRole, Role
from app.models.user import User


# --------------------------------------------------------------------------- #
# Directory access
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_owner_can_list_and_inspect_users(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    directory = await client.get(
        "/api/v1/users", headers={"X-Test-User": owner.username}
    )
    assert directory.status_code == 200
    ids = {u["id"] for u in directory.json()}
    assert str(owner.id) in ids and str(target.id) in ids

    detail = await client.get(
        f"/api/v1/users/{target.id}", headers={"X-Test-User": owner.username}
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["email"] == target.email
    assert body["role"] == "customer"
    assert "created_at" in body
    # Internal fields must not leak.
    assert "clerk_id" not in body
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_customer_cannot_list_users(client, make_user):
    customer = await make_user()
    response = await client.get(
        "/api/v1/users", headers={"X-Test-User": customer.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_cannot_list_users(client, make_user):
    agent = await make_user(role=Role.AGENT)
    response = await client.get(
        "/api/v1/users", headers={"X-Test-User": agent.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_agent_cannot_change_roles(client, make_user):
    agent = await make_user(role=Role.AGENT)
    target = await make_user()
    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": agent.username},
        json={"role": "admin"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Owner role changes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start_role,new_role",
    [
        (Role.CUSTOMER, "agent"),
        (Role.CUSTOMER, "admin"),
        (Role.AGENT, "customer"),
        (Role.ADMIN, "customer"),
        (Role.AGENT, "admin"),
        (Role.ADMIN, "agent"),
    ],
)
async def test_owner_can_change_roles(client, make_user, start_role, new_role):
    owner = await make_user(role=Role.OWNER)
    target = await make_user(role=start_role)

    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": new_role},
    )
    assert response.status_code == 200
    assert response.json()["role"] == new_role


@pytest.mark.asyncio
async def test_role_change_persists(client, make_user, session_factory):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "agent"},
    )

    # Read it back in a fresh session: the change is committed to the database.
    async with session_factory() as session:
        stored = await session.get(User, target.id)
        assert stored is not None
        assert stored.role == Role.AGENT


@pytest.mark.asyncio
async def test_repeated_role_change_is_idempotent(client, make_user, session_factory):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    for role in ("agent", "agent", "admin", "admin", "customer"):
        response = await client.patch(
            f"/api/v1/users/{target.id}/role",
            headers={"X-Test-User": owner.username},
            json={"role": role},
        )
        assert response.status_code == 200

    async with session_factory() as session:
        users = (await session.exec(select(User))).all()
    # No duplicate rows were created.
    assert sum(1 for u in users if u.id == target.id) == 1


# --------------------------------------------------------------------------- #
# OWNER can never be requested
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_role_endpoint_rejects_owner_value(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "owner"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generic_update_rejects_owner_value(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers={"X-Test-User": owner.username},
        json={"role": "owner"},
    )
    assert response.status_code == 422


def test_assignable_role_excludes_owner():
    assert [r.value for r in AssignableRole] == ["customer", "agent", "admin"]
    with pytest.raises(ValueError):
        AssignableRole("owner")


# --------------------------------------------------------------------------- #
# Owner protection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_owner_cannot_change_own_role(client, make_user):
    owner = await make_user(role=Role.OWNER)

    response = await client.patch(
        f"/api/v1/users/{owner.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "customer"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_owner_cannot_deactivate_self(client, make_user):
    owner = await make_user(role=Role.OWNER)

    response = await client.patch(
        f"/api/v1/users/{owner.id}/status",
        headers={"X-Test-User": owner.username},
        json={"is_active": False},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_owner_account_cannot_be_demoted_by_another_actor(
    session_factory, make_user
):
    """Owner protection holds even when the actor is not the Owner (guard-level)."""
    from fastapi import HTTPException

    from app.api.routers.users import _guard_managed_user_change

    owner = await make_user(role=Role.OWNER)
    actor = await make_user(role=Role.ADMIN)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as excinfo:
            await _guard_managed_user_change(
                session, actor, owner, {"role": Role.CUSTOMER}
            )
    assert excinfo.value.status_code == 400

    async with session_factory() as session:
        with pytest.raises(HTTPException) as excinfo:
            await _guard_managed_user_change(
                session, actor, owner, {"is_active": False}
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_cannot_demote_or_deactivate_owner_over_http(client, make_user):
    owner = await make_user(role=Role.OWNER)
    admin = await make_user(role=Role.ADMIN)

    demote = await client.patch(
        f"/api/v1/users/{owner.id}/role",
        headers={"X-Test-User": admin.username},
        json={"role": "customer"},
    )
    assert demote.status_code == 403

    deactivate = await client.patch(
        f"/api/v1/users/{owner.id}/status",
        headers={"X-Test-User": admin.username},
        json={"is_active": False},
    )
    assert deactivate.status_code == 403


# --------------------------------------------------------------------------- #
# Status changes / errors
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_owner_can_deactivate_and_reactivate_user(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    off = await client.patch(
        f"/api/v1/users/{target.id}/status",
        headers={"X-Test-User": owner.username},
        json={"is_active": False},
    )
    assert off.status_code == 200
    assert off.json()["is_active"] is False

    on = await client.patch(
        f"/api/v1/users/{target.id}/status",
        headers={"X-Test-User": owner.username},
        json={"is_active": True},
    )
    assert on.status_code == 200
    assert on.json()["is_active"] is True


@pytest.mark.asyncio
async def test_role_change_unknown_user_returns_404(client, make_user):
    owner = await make_user(role=Role.OWNER)
    response = await client.patch(
        f"/api/v1/users/{uuid.uuid4()}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "agent"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_status_change_unknown_user_returns_404(client, make_user):
    owner = await make_user(role=Role.OWNER)
    response = await client.patch(
        f"/api/v1/users/{uuid.uuid4()}/status",
        headers={"X-Test-User": owner.username},
        json={"is_active": False},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_role_change_requires_authentication(client, make_user):
    target = await make_user()
    response = await client.patch(
        f"/api/v1/users/{target.id}/role", json={"role": "agent"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_owner_is_denied(client, make_user):
    owner = await make_user(role=Role.OWNER, is_active=False)
    response = await client.get(
        "/api/v1/users", headers={"X-Test-User": owner.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_invalid_role_body_is_rejected(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()
    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "wizard"},
    )
    assert response.status_code == 422
