import pytest
from sqlmodel import select

from app.enums.enums import Role
from app.models.user import User


@pytest.mark.asyncio
async def test_get_me_returns_profile(client, make_user):
    user = await make_user()
    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": user.username}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == user.username
    assert body["role"] == "customer"
    # Sensitive/internal fields must never leak.
    assert "password_hash" not in body
    assert "clerk_id" not in body


@pytest.mark.asyncio
async def test_patch_me_updates_allowed_fields(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"full_name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


@pytest.mark.asyncio
async def test_patch_me_rejects_role_change(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"role": "admin"},
    )
    # The request schema forbids unknown fields, so a role change is a 422.
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_me_duplicate_username_conflict(client, make_user):
    await make_user(username="taken")
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"username": "taken"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_patch_me_rejects_another_users_email(client, make_user, session_factory):
    """An authenticated user cannot claim another account's email address."""
    victim = await make_user(username="victim", email="victim@example.com")
    attacker = await make_user(username="attacker", email="attacker@example.com")

    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": attacker.username},
        json={"email": victim.email},
    )
    assert response.status_code == 422
    assert "managed by Clerk" in response.json()["detail"]

    async with session_factory() as session:
        attacker_row = await session.get(User, attacker.id)
        victim_row = await session.get(User, victim.id)
        assert attacker_row is not None and victim_row is not None
        assert attacker_row.email == "attacker@example.com"
        assert victim_row.email == "victim@example.com"
        assert victim_row.clerk_id == f"test_{victim.username}"


@pytest.mark.asyncio
async def test_patch_me_rejects_unclaimed_email(client, make_user, session_factory):
    """Even an unused address cannot be pre-claimed through the profile API."""
    attacker = await make_user(username="squatter", email="squatter@example.com")

    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": attacker.username},
        json={"email": "future.person@example.com"},
    )
    assert response.status_code == 422

    async with session_factory() as session:
        stored = await session.get(User, attacker.id)
        assert stored is not None
        assert stored.email == "squatter@example.com"
        preclaimed = (
            await session.exec(
                select(User).where(User.email == "future.person@example.com")
            )
        ).first()
        assert preclaimed is None


@pytest.mark.asyncio
async def test_patch_me_allows_unchanged_email_with_profile_update(client, make_user):
    """Older clients may submit the whole form; an unchanged email is a no-op."""
    user = await make_user()
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"full_name": "Updated Name", "email": user.email.upper()},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"
    assert response.json()["email"] == user.email


@pytest.mark.asyncio
async def test_owner_cannot_change_a_users_email(client, make_user):
    """Email stays Clerk-authoritative even for the Owner's management API."""
    owner = await make_user(role=Role.OWNER)
    target = await make_user(username="managed", email="managed@example.com")

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers={"X-Test-User": owner.username},
        json={"email": "replacement@example.com"},
    )
    assert response.status_code == 422
    assert "managed by Clerk" in response.json()["detail"]

    detail = await client.get(
        f"/api/v1/users/{target.id}", headers={"X-Test-User": owner.username}
    )
    assert detail.json()["email"] == "managed@example.com"


@pytest.mark.asyncio
async def test_missing_authentication_returns_401(client):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_inactive_user_returns_403(client, make_user):
    user = await make_user(is_active=False)
    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": user.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_me_works_for_all_roles(client, make_user):
    for role in (Role.CUSTOMER, Role.AGENT, Role.ADMIN, Role.OWNER):
        user = await make_user(role=role)
        response = await client.get(
            "/api/v1/users/me", headers={"X-Test-User": user.username}
        )
        assert response.status_code == 200
        assert response.json()["role"] == role.value
