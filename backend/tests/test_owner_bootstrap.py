"""Tests for the one-time Owner bootstrap command and Owner invariants.

These exercise ``app.commands.bootstrap_owner.promote_owner`` against an
isolated in-memory SQLite database with Clerk mocked. The real bootstrap is
*not* run against any configured database here.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.commands.bootstrap_owner import BootstrapError, promote_owner
from app.enums.enums import Role
from app.models.user import User

# --------------------------------------------------------------------------- #
# Clerk fakes
# --------------------------------------------------------------------------- #


class _FakeEmail:
    def __init__(self, address: str, status: str) -> None:
        self.id = "email_1"
        self.email_address = address
        self.verification = SimpleNamespace(status=SimpleNamespace(value=status))


class _FakeClerkUser:
    """Stand-in for the Clerk SDK ``User`` model used by the bootstrap flow.

    The real ``clerk_backend_api.models.User`` exposes ``username``,
    ``first_name`` and ``last_name`` as *nullable* optional attributes: the
    attributes are always present on the model but their value may be ``None``.
    The double mirrors that contract so app code that reads these fields is
    exercised the same way it would be in production.
    """

    def __init__(
        self,
        email: str,
        status: str = "verified",
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        self.primary_email_address_id = "email_1"
        self.email_addresses = [_FakeEmail(email, status)]
        self.username = username
        self.first_name = first_name
        self.last_name = last_name


class _FakeUsers:
    def __init__(
        self, user: _FakeClerkUser | None = None, *, error: bool = False
    ) -> None:
        self._user = user
        self._error = error

    async def get_async(self, user_id: str) -> _FakeClerkUser:
        if self._error:
            raise RuntimeError("clerk unavailable")
        assert self._user is not None
        return self._user


class _FakeClerk:
    def __init__(self, users: _FakeUsers) -> None:
        self.users = users


def _clerk(email: str, status: str = "verified") -> _FakeClerk:
    return _FakeClerk(_FakeUsers(_FakeClerkUser(email, status)))


def _clerk_error() -> _FakeClerk:
    return _FakeClerk(_FakeUsers(error=True))


# --------------------------------------------------------------------------- #
# Settings normalization
# --------------------------------------------------------------------------- #


def test_settings_normalizes_initial_admin_email(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "INITIAL_ADMIN_EMAIL", "  Boss@Example.COM ")
    assert config.settings.initial_admin_email == "boss@example.com"

    monkeypatch.setattr(config.settings, "INITIAL_ADMIN_EMAIL", "   ")
    assert config.settings.initial_admin_email is None


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_promotes_verified_matching_identity(session_factory, make_user):
    user = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )

    async with session_factory() as session:
        promoted = await promote_owner(
            session,
            clerk=_clerk("boss@example.com"),
            configured_email="boss@example.com",
        )

    assert promoted.id == user.id
    assert promoted.role == Role.OWNER
    assert promoted.clerk_id == f"test_{user.username}"

    async with session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.role == Role.OWNER


@pytest.mark.asyncio
async def test_bootstrap_preserves_primary_key_and_tickets(
    session_factory, make_user, make_ticket
):
    user = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )
    ticket = await make_ticket(user)

    async with session_factory() as session:
        await promote_owner(
            session,
            clerk=_clerk("boss@example.com"),
            configured_email="boss@example.com",
        )

    async with session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.id == user.id
        assert stored.role == Role.OWNER

        from app.models.ticket import Ticket

        refreshed_ticket = await session.get(Ticket, ticket.id)
        assert refreshed_ticket is not None
        assert refreshed_ticket.created_by_user_id == user.id


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_refuses_missing_configuration(session_factory):
    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(session, clerk=_clerk_error(), configured_email=None)


@pytest.mark.asyncio
async def test_refuses_when_owner_already_exists(session_factory, make_user):
    await make_user(role=Role.OWNER, username="owner", email="owner@example.com")
    target = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("boss@example.com"),
                configured_email="boss@example.com",
            )

    async with session_factory() as session:
        stored = await session.get(User, target.id)
        assert stored is not None
        assert stored.role == Role.CUSTOMER


@pytest.mark.asyncio
async def test_rerun_after_success_reports_already_established(
    session_factory, make_user
):
    await make_user(role=Role.CUSTOMER, username="boss", email="boss@example.com")

    async with session_factory() as session:
        await promote_owner(
            session,
            clerk=_clerk("boss@example.com"),
            configured_email="boss@example.com",
        )

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("boss@example.com"),
                configured_email="boss@example.com",
            )

    async with session_factory() as session:
        owners = (await session.exec(select(User).where(User.role == Role.OWNER))).all()
        assert len(owners) == 1


@pytest.mark.asyncio
async def test_refuses_no_matching_local_account(session_factory, make_user):
    await make_user(role=Role.CUSTOMER, username="someone", email="someone@example.com")

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("boss@example.com"),
                configured_email="boss@example.com",
            )


@pytest.mark.asyncio
async def test_refuses_unlinked_local_account(session_factory):
    async with session_factory() as session:
        session.add(
            User(
                clerk_id=None,
                full_name="Unlinked",
                username="unlinked",
                email="boss@example.com",
                role=Role.CUSTOMER,
            )
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("boss@example.com"),
                configured_email="boss@example.com",
            )


@pytest.mark.asyncio
async def test_refuses_inactive_account(session_factory, make_user):
    await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com", is_active=False
    )

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("boss@example.com"),
                configured_email="boss@example.com",
            )


@pytest.mark.asyncio
async def test_refuses_unverified_clerk_identity(session_factory, make_user):
    user = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("boss@example.com", status="unverified"),
                configured_email="boss@example.com",
            )

    async with session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.role == Role.CUSTOMER


@pytest.mark.asyncio
async def test_refuses_email_mismatch(session_factory, make_user):
    user = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session,
                clerk=_clerk("mallory@example.com"),
                configured_email="boss@example.com",
            )

    async with session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.role == Role.CUSTOMER


@pytest.mark.asyncio
async def test_refuses_when_clerk_unreachable(session_factory, make_user):
    user = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )

    async with session_factory() as session:
        with pytest.raises(BootstrapError):
            await promote_owner(
                session, clerk=_clerk_error(), configured_email="boss@example.com"
            )

    async with session_factory() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.role == Role.CUSTOMER


@pytest.mark.asyncio
async def test_database_prevents_multiple_owners(session_factory, make_user):
    await make_user(role=Role.OWNER, username="owner_a", email="owner_a@example.com")

    with pytest.raises(IntegrityError):
        await make_user(
            role=Role.OWNER, username="owner_b", email="owner_b@example.com"
        )


# --------------------------------------------------------------------------- #
# Ownership survives configuration changes / never granted to signups
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_removing_bootstrap_setting_keeps_owner(
    client, session_factory, make_user, monkeypatch
):
    from app.core import auth, config

    user = await make_user(
        role=Role.CUSTOMER, username="boss", email="boss@example.com"
    )

    async with session_factory() as session:
        await promote_owner(
            session,
            clerk=_clerk("boss@example.com"),
            configured_email="boss@example.com",
        )

    # The runtime setting is removed entirely; no request-time path may demote.
    monkeypatch.setattr(config.settings, "INITIAL_ADMIN_EMAIL", None)

    class _ExplodingUsers:
        async def get_async(self, user_id: str):
            raise AssertionError("Clerk must not be queried on the request path")

    monkeypatch.setattr(auth, "clerk_client", SimpleNamespace(users=_ExplodingUsers()))

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": user.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"


@pytest.mark.asyncio
async def test_new_signup_is_never_owner(client, session_factory, monkeypatch):
    from app.core import auth

    class _NewUsers:
        async def get_async(self, user_id: str) -> _FakeClerkUser:
            return _FakeClerkUser("newcomer@example.com")

    monkeypatch.setattr(auth, "clerk_client", SimpleNamespace(users=_NewUsers()))

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "newcomer"})
    assert response.status_code == 200
    assert response.json()["role"] == "customer"

    async with session_factory() as session:
        stored = (
            await session.exec(select(User).where(User.email == "newcomer@example.com"))
        ).first()
        assert stored is not None
        assert stored.role == Role.CUSTOMER
        # ``username`` is null on the Clerk identity, so provisioning falls back
        # to the verified email's local part; it is never derived from a role or
        # from the environment.
        assert stored.username.startswith("newcomer_")


@pytest.mark.asyncio
async def test_provisioning_tolerates_absent_optional_clerk_fields(
    client, session_factory, monkeypatch
):
    """A Clerk user object without the optional attributes still provisions.

    Guards the regression where ``clerk_user.username`` raised ``AttributeError``
    when the attribute was absent, rather than being present and ``None``.
    """
    from app.core import auth

    class _BareClerkUser:
        """Only the fields provisioning must rely on; optional ones are absent."""

        def __init__(self, email: str) -> None:
            self.primary_email_address_id = "email_1"
            self.email_addresses = [_FakeEmail(email, "verified")]

    class _NewUsers:
        async def get_async(self, user_id: str) -> _BareClerkUser:
            return _BareClerkUser("bare@example.com")

    monkeypatch.setattr(auth, "clerk_client", SimpleNamespace(users=_NewUsers()))

    response = await client.get("/api/v1/users/me", headers={"X-Test-User": "bare"})
    assert response.status_code == 200
    assert response.json()["role"] == "customer"

    async with session_factory() as session:
        stored = (
            await session.exec(select(User).where(User.email == "bare@example.com"))
        ).first()
        assert stored is not None
        assert stored.role == Role.CUSTOMER
        assert stored.username.startswith("bare_")
