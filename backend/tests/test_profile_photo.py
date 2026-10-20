"""Profile-photo feature coverage.

Covers the backend half of the Clerk-synced avatar:

* the ``users.image_url`` field is exposed on the read schemas;
* it is populated from **verified Clerk data** during provisioning;
* the explicit ``POST /users/me/avatar`` sync re-reads it from Clerk;
* a client can never store an arbitrary URL (the sync ignores the request body
  and ``PATCH /users/me`` forbids unknown fields);
* failures map to clear status codes.

The frontend upload path (``user.setProfileImage``) is Clerk-owned and is not
exercised here; these tests guarantee the server-side contract it relies on.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.enums.enums import Role
from app.models import User

pytestmark = pytest.mark.asyncio


class _FakeEmail:
    def __init__(self, address: str, status: str = "verified") -> None:
        self.id = "email_1"
        self.verification = SimpleNamespace(status=SimpleNamespace(value=status))
        self.email_address = address


class _FakeClerkUser:
    def __init__(self, email: str, image_url: str | None) -> None:
        self.primary_email_address_id = "email_1"
        self.email_addresses = [_FakeEmail(email)]
        self.username = "someone"
        self.first_name = "Some"
        self.last_name = "One"
        self.image_url = image_url


class _FakeUsers:
    def __init__(
        self, user: _FakeClerkUser | None = None, error: Exception | None = None
    ):
        self._user = user
        self._error = error
        self.calls = 0

    async def get_async(self, user_id: str) -> _FakeClerkUser:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._user


def _install_clerk(monkeypatch, users: _FakeUsers):
    """Patch the Clerk client everywhere it is referenced.

    ``app.core.auth`` uses it during provisioning; the users router imports the
    name directly, so both module attributes must point at the fake.
    """
    from app.api.routers import users as users_router
    from app.core import auth

    fake = SimpleNamespace(users=users)
    monkeypatch.setattr(auth, "clerk_client", fake)
    monkeypatch.setattr(users_router, "clerk_client", fake)
    return users


def _patch_clerk(
    monkeypatch, *, image_url: str | None, email: str = "someone@example.com"
):
    return _install_clerk(monkeypatch, _FakeUsers(_FakeClerkUser(email, image_url)))


def _patch_clerk_error(monkeypatch):
    return _install_clerk(
        monkeypatch, _FakeUsers(error=RuntimeError("clerk unavailable"))
    )


async def test_me_exposes_image_url_field(client, make_user):
    await make_user(username="avataruser", email="avataruser@example.com")
    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": "avataruser"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "image_url" in body
    assert body["image_url"] is None


async def test_provisioning_caches_clerk_image_url(
    client, session_factory, monkeypatch
):
    _patch_clerk(
        monkeypatch,
        image_url="https://img.clerk.test/provisioned.png",
        email="provisioned@example.com",
    )
    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": "provisioned"}
    )
    assert response.status_code == 200
    assert response.json()["image_url"] == "https://img.clerk.test/provisioned.png"

    async with session_factory() as session:
        found = (
            await session.exec(
                select(User).where(User.email == "provisioned@example.com")
            )
        ).first()
        assert found is not None
        assert found.image_url == "https://img.clerk.test/provisioned.png"


async def test_avatar_sync_success(client, make_user, session_factory, monkeypatch):
    user = await make_user(username="syncuser", email="syncuser@example.com")
    users = _patch_clerk(monkeypatch, image_url="https://img.clerk.test/uploaded.png")

    response = await client.post(
        "/api/v1/users/me/avatar", headers={"X-Test-User": "syncuser"}
    )
    assert response.status_code == 200
    assert response.json()["image_url"] == "https://img.clerk.test/uploaded.png"
    assert users.calls >= 1

    async with session_factory() as session:
        refreshed = await session.get(User, user.id)
        assert refreshed.image_url == "https://img.clerk.test/uploaded.png"


async def test_avatar_sync_ignores_request_body(
    client, make_user, session_factory, monkeypatch
):
    """A client cannot store an arbitrary URL: the value always comes from Clerk."""
    user = await make_user(username="eviluser", email="eviluser@example.com")
    _patch_clerk(monkeypatch, image_url="https://img.clerk.test/real.png")

    response = await client.post(
        "/api/v1/users/me/avatar",
        headers={"X-Test-User": "eviluser"},
        json={"image_url": "https://evil.example.com/tracker.png"},
    )
    assert response.status_code == 200
    assert response.json()["image_url"] == "https://img.clerk.test/real.png"

    async with session_factory() as session:
        refreshed = await session.get(User, user.id)
        assert refreshed.image_url == "https://img.clerk.test/real.png"


async def test_avatar_sync_clerk_failure_returns_502(client, make_user, monkeypatch):
    await make_user(username="failuser", email="failuser@example.com")
    _patch_clerk_error(monkeypatch)

    response = await client.post(
        "/api/v1/users/me/avatar", headers={"X-Test-User": "failuser"}
    )
    assert response.status_code == 502


async def test_profile_update_cannot_set_image_url(client, make_user):
    """``UserUpdate`` forbids unknown fields, so the photo can't be set via PATCH."""
    await make_user(username="patchuser", email="patchuser@example.com")
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": "patchuser"},
        json={"image_url": "https://evil.example.com/x.png"},
    )
    assert response.status_code == 422


async def test_avatar_sync_without_clerk_link_conflicts(session_factory):
    """A record with no Clerk identity cannot sync a Clerk photo (direct unit)."""
    from app.api.routers import users as users_router

    async with session_factory() as session:
        user = User(
            clerk_id=None,
            full_name="No Link",
            username="nolink",
            email="nolink@example.com",
            role=Role.CUSTOMER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        with pytest.raises(HTTPException) as exc:
            await users_router.sync_my_avatar(session=session, user=user)
        assert exc.value.status_code == 409
