import pytest

from app.enums.enums import Role


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
