"""Focused tests for behaviors that were not covered by the existing suite.

Added during the verification pass. They exercise real routers and the real
``get_current_user`` dependency (Clerk's network client is mocked) so they do
not need PostgreSQL or Clerk credentials.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlmodel import select

from app.enums.enums import NotificationType, Role, TicketStatus
from app.models.attachment import Attachment
from app.models.notification import Notification
from app.models.user import User


# --------------------------------------------------------------------------- #
# Authentication: lazy provisioning + linking (mocked Clerk)
# --------------------------------------------------------------------------- #


class _FakeEmail:
    def __init__(self, email_id: str, address: str, status: str) -> None:
        self.id = email_id
        self.email_address = address
        self.verification = SimpleNamespace(status=SimpleNamespace(value=status))


class _FakeClerkUser:
    def __init__(self, email: str, status: str = "verified") -> None:
        self.primary_email_address_id = "email_1"
        self.email_addresses = [_FakeEmail("email_1", email, status)]
        self.username = "newuser"
        self.first_name = "New"
        self.last_name = "User"


class _FakeUsers:
    def __init__(self, user: _FakeClerkUser) -> None:
        self._user = user
        self.calls = 0

    async def get_async(self, user_id: str) -> _FakeClerkUser:
        self.calls += 1
        return self._user


class _FakeClerk:
    def __init__(self, user: _FakeClerkUser) -> None:
        self.users = _FakeUsers(user)


def _patch_clerk(monkeypatch, email: str, status: str = "verified") -> _FakeClerk:
    from app.core import auth

    fake = _FakeClerk(_FakeClerkUser(email, status))
    monkeypatch.setattr(auth, "clerk_client", fake)
    return fake


@pytest.mark.asyncio
async def test_new_clerk_user_is_provisioned_as_customer(
    client, session_factory, monkeypatch
):
    _patch_clerk(monkeypatch, "brandnew@example.com")

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "brandnew"})
    assert response.status_code == 200
    assert response.json()["role"] == "customer"

    async with session_factory() as session:
        found = (
            await session.exec(select(User).where(User.email == "brandnew@example.com"))
        ).first()
        assert found is not None
        assert found.role == Role.CUSTOMER
        assert found.is_active is True


@pytest.mark.asyncio
async def test_existing_email_is_linked_to_clerk_identity(
    client, make_user, session_factory, monkeypatch
):
    existing = await make_user(username="legacy", email="legacy@example.com")
    _patch_clerk(monkeypatch, "legacy@example.com")

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "legacy"})
    assert response.status_code == 200
    assert response.json()["id"] == str(existing.id)

    async with session_factory() as session:
        refreshed = await session.get(User, existing.id)
        assert refreshed.clerk_id == "test_legacy"


@pytest.mark.asyncio
async def test_unverified_email_is_rejected(client, monkeypatch):
    _patch_clerk(monkeypatch, "unverified@example.com", status="unverified")

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "someone"})
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Notifications: read-all is scoped to the caller
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_read_all_only_affects_current_user(
    client, make_user, make_ticket, session_factory
):
    from app.services.notifications import create_notification

    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(alice)

    async with session_factory() as session:
        create_notification(
            session,
            recipient_user_id=alice.id,
            related_ticket_id=ticket.id,
            type=NotificationType.STATUS_CHANGED,
            title="A",
            message="Alice notice",
        )
        create_notification(
            session,
            recipient_user_id=bob.id,
            related_ticket_id=ticket.id,
            type=NotificationType.STATUS_CHANGED,
            title="B",
            message="Bob notice",
        )
        await session.commit()

    response = await client.post(
        "/api/v1/notifications/read-all", headers={"X-Test-User": alice.username}
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 1

    async with session_factory() as session:
        bob_unread = (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == bob.id,
                    Notification.is_read.is_(False),
                )
            )
        ).all()
        assert len(bob_unread) == 1


# --------------------------------------------------------------------------- #
# Attachments: size limit, ownership, path traversal
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_attachment_size_limit(client, make_user, make_ticket, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 5)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("big.txt", b"way more than five bytes", "text/plain")},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_cannot_download_foreign_attachment(client, make_user, make_ticket):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    upload = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": bob.username},
        files={"file": ("note.txt", b"secret", "text/plain")},
    )
    assert upload.status_code == 201
    attachment_id = upload.json()["id"]

    response = await client.get(
        f"/api/v1/attachments/{attachment_id}/download",
        headers={"X-Test-User": alice.username},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_attachment_path_traversal_is_blocked(
    client, make_user, make_ticket, session_factory
):
    customer = await make_user()
    ticket = await make_ticket(customer)

    async with session_factory() as session:
        attachment = Attachment(
            ticket_id=ticket.id,
            uploaded_by_user_id=customer.id,
            original_filename="passwd",
            storage_key="../../etc/passwd",
            content_type="text/plain",
            size_bytes=10,
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)
        attachment_id = attachment.id

    response = await client.get(
        f"/api/v1/attachments/{attachment_id}/download",
        headers={"X-Test-User": customer.username},
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Comments / tickets: forged authorship, validation, scoping, pagination
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_comment_authorship_cannot_be_forged(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)
    other = await make_user()

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
        json={"body": "hi", "author_user_id": str(other.id)},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ticket_creation_requires_title_and_description(client, make_user):
    customer = await make_user()
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={"description": "no title"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_customer_cannot_modify_foreign_ticket(client, make_user, make_ticket):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": alice.username},
        json={"title": "hijack"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ticket_list_pagination_and_status_filter(client, make_user, make_ticket):
    customer = await make_user()
    await make_ticket(customer, status=TicketStatus.OPEN)
    await make_ticket(customer, status=TicketStatus.CLOSED)
    await make_ticket(customer, status=TicketStatus.OPEN)

    page = await client.get(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        params={"limit": 1, "offset": 1},
    )
    assert page.status_code == 200
    assert len(page.json()) == 1

    filtered = await client.get(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        params={"status": "OPEN"},
    )
    assert filtered.status_code == 200
    assert {t["status"] for t in filtered.json()} == {"OPEN"}
    assert len(filtered.json()) == 2


# --------------------------------------------------------------------------- #
# Admin user detail authorization
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admin_user_detail_authorization(client, make_user):
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    target = await make_user()

    denied = await client.get(
        f"/api/v1/users/{target.id}", headers={"X-Test-User": customer.username}
    )
    assert denied.status_code == 403

    allowed = await client.get(
        f"/api/v1/users/{target.id}", headers={"X-Test-User": admin.username}
    )
    assert allowed.status_code == 200
    assert allowed.json()["id"] == str(target.id)

    missing = await client.get(
        f"/api/v1/users/{uuid.uuid4()}", headers={"X-Test-User": admin.username}
    )
    assert missing.status_code == 404


# --------------------------------------------------------------------------- #
# Clerk provisioning edge cases (regression coverage for the production 500s)
# --------------------------------------------------------------------------- #


class _RawClerkUser:
    """A Clerk user stand-in whose attributes are supplied verbatim.

    Lets us model the optional/absent fields the real SDK permits without
    relying on the shared ``_FakeClerkUser`` shape.
    """

    def __init__(
        self,
        *,
        primary_email_address_id: str | None,
        email_addresses: list,
        username: object = None,
        first_name: object = None,
        last_name: object = None,
    ) -> None:
        self.primary_email_address_id = primary_email_address_id
        self.email_addresses = email_addresses
        self.username = username
        self.first_name = first_name
        self.last_name = last_name


class _RawUsers:
    def __init__(self, *, user=None, error: Exception | None = None) -> None:
        self._user = user
        self._error = error

    async def get_async(self, user_id: str):
        if self._error is not None:
            raise self._error
        return self._user


def _patch_clerk_raw(monkeypatch, users: _RawUsers) -> None:
    from app.core import auth

    monkeypatch.setattr(auth, "clerk_client", SimpleNamespace(users=users))


@pytest.mark.asyncio
async def test_empty_username_uses_email_local_part(
    client, session_factory, monkeypatch
):
    """An empty (not ``None``) Clerk username falls back to the email local part."""
    _patch_clerk_raw(
        monkeypatch,
        _RawUsers(
            user=_RawClerkUser(
                primary_email_address_id="email_1",
                email_addresses=[
                    _FakeEmail("email_1", "emptyuser@example.com", "verified")
                ],
                username="",
            )
        ),
    )

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": "emptyuser"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "customer"

    async with session_factory() as session:
        stored = (
            await session.exec(
                select(User).where(User.email == "emptyuser@example.com")
            )
        ).first()
        assert stored is not None
        assert stored.username.startswith("emptyuser_")


@pytest.mark.asyncio
async def test_linking_preserves_existing_privileged_role(
    client, session_factory, monkeypatch
):
    """Linking an unlinked local ADMIN to Clerk keeps the stored role."""
    async with session_factory() as session:
        legacy = User(
            clerk_id=None,
            full_name="Legacy Admin",
            username="legacyadmin",
            email="legacyadmin@example.com",
            role=Role.ADMIN,
        )
        session.add(legacy)
        await session.commit()
        await session.refresh(legacy)
        legacy_id = legacy.id

    _patch_clerk(monkeypatch, "legacyadmin@example.com")

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": "newclerkid"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    async with session_factory() as session:
        refreshed = await session.get(User, legacy_id)
        assert refreshed is not None
        assert refreshed.role == Role.ADMIN
        assert refreshed.clerk_id == "test_newclerkid"


@pytest.mark.asyncio
async def test_signup_email_linked_to_another_clerk_account_conflicts(
    client, make_user, monkeypatch
):
    """A verified email already bound to a different Clerk id is a 409."""
    await make_user(username="other", email="conflict@example.com")
    _patch_clerk(monkeypatch, "conflict@example.com")

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": "different"}
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_missing_primary_email_is_a_controlled_403(client, monkeypatch):
    """A Clerk identity without a primary email never produces a 500."""
    _patch_clerk_raw(
        monkeypatch,
        _RawUsers(
            user=_RawClerkUser(
                primary_email_address_id=None,
                email_addresses=[
                    _FakeEmail("email_1", "orphan@example.com", "verified")
                ],
            )
        ),
    )

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "orphan"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_empty_primary_email_is_a_controlled_403(client, monkeypatch):
    """A blank primary email address never produces a 500."""
    _patch_clerk_raw(
        monkeypatch,
        _RawUsers(
            user=_RawClerkUser(
                primary_email_address_id="email_1",
                email_addresses=[_FakeEmail("email_1", "   ", "verified")],
            )
        ),
    )

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "blank"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_clerk_lookup_failure_returns_502_not_500(client, monkeypatch):
    """An unavailable Clerk Backend API surfaces as 502, never 500."""
    _patch_clerk_raw(monkeypatch, _RawUsers(error=RuntimeError("clerk unavailable")))

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": "clerkdown"}
    )
    assert response.status_code == 502
