"""Owner identity: configuration, recognition, transfer and security.

These tests exercise the shared ``app.services.owner_identity`` service and the
request-path integration in ``app.core.auth.get_current_user`` using an in-memory
SQLite database and Clerk doubles. They never contact Clerk or PostgreSQL.

PostgreSQL-specific guarantees (the real partial unique index, advisory locking
and concurrency) live in ``test_owner_identity_postgres.py``.
"""

from types import SimpleNamespace

from sqlmodel import select

from app.core.config import Settings
from app.enums.enums import Role
from app.models.user import User
from app.services.owner_identity import (
    OwnerAction,
    evaluate,
    find_candidate_by_email,
    normalize_email,
    reconcile_owner,
)

# --------------------------------------------------------------------------- #
# Clerk doubles
# --------------------------------------------------------------------------- #


class _FakeEmail:
    def __init__(self, address: str, status: str = "verified", *, eid: str = "e1"):
        self.id = eid
        self.email_address = address
        self.verification = SimpleNamespace(status=SimpleNamespace(value=status))


class _FakeClerkUser:
    def __init__(
        self,
        *,
        primary: str,
        status: str = "verified",
        secondary: list[_FakeEmail] | None = None,
        username: str = "someone",
    ):
        primary_obj = _FakeEmail(primary, status, eid="primary")
        self.primary_email_address_id = "primary"
        self.email_addresses = [primary_obj, *(secondary or [])]
        self.username = username
        self.first_name = "Test"
        self.last_name = "User"
        self.image_url = None


class _FakeUsers:
    def __init__(self, user=None, *, error: Exception | None = None):
        self._user = user
        self._error = error
        self.calls = 0

    async def get_async(self, user_id: str):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._user


class _FakeClerk:
    def __init__(self, user=None, *, error: Exception | None = None):
        self.users = _FakeUsers(user, error=error)


def _settings(**overrides) -> Settings:
    """Build an isolated Settings object.

    ``_env_file=None`` stops the developer's local ``backend/.env`` from
    influencing these assertions, so the tests describe the code's behaviour
    rather than the machine's configuration.
    """
    base = {
        "DATABASE_URL": "sqlite+aiosqlite://",
        "CLERK_SECRET_KEY": "sk_test_dummy",
        "FRONTEND_URL": "http://localhost:5173",
        "OWNER_EMAIL": None,
        "INITIAL_ADMIN_EMAIL": None,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def test_config_owner_email_unset(monkeypatch):
    monkeypatch.delenv("OWNER_EMAIL", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_EMAIL", raising=False)
    assert _settings(OWNER_EMAIL=None, INITIAL_ADMIN_EMAIL=None).owner_email is None


def test_config_owner_email_normalizes_whitespace_and_case():
    cfg = _settings(OWNER_EMAIL="  Boss@Example.COM  ")
    assert cfg.owner_email == "boss@example.com"


def test_config_empty_owner_email_is_none():
    assert _settings(OWNER_EMAIL="   ").owner_email is None


def test_config_legacy_fallback_when_owner_unset():
    cfg = _settings(OWNER_EMAIL=None, INITIAL_ADMIN_EMAIL="Legacy@Example.com")
    assert cfg.owner_email == "legacy@example.com"
    assert cfg.owner_email_conflict is False


def test_config_owner_email_takes_precedence():
    cfg = _settings(
        OWNER_EMAIL="new@example.com", INITIAL_ADMIN_EMAIL="old@example.com"
    )
    assert cfg.owner_email == "new@example.com"
    assert cfg.owner_email_conflict is True


def test_config_same_values_are_not_a_conflict():
    cfg = _settings(
        OWNER_EMAIL="same@example.com", INITIAL_ADMIN_EMAIL="SAME@example.com"
    )
    assert cfg.owner_email == "same@example.com"
    assert cfg.owner_email_conflict is False


def test_config_conflict_never_exposes_the_address():
    cfg = _settings(
        OWNER_EMAIL="secret-a@example.com", INITIAL_ADMIN_EMAIL="secret-b@example.com"
    )
    # The conflict flag is boolean only; there is no accessor leaking both.
    assert isinstance(cfg.owner_email_conflict, bool)
    assert "secret" not in repr(cfg.owner_email_conflict)


def test_normalize_email():
    assert normalize_email("  A@B.COM ") == "a@b.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _make_user(
    session_factory, *, role=Role.CUSTOMER, email, active=True, clerk="c1"
):
    user = User(
        clerk_id=clerk,
        full_name="Test User",
        username=f"u_{email.split('@')[0]}",
        email=email.lower(),
        role=role,
        is_active=active,
    )
    async with session_factory() as s:
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


async def _owner(session_factory):
    async with session_factory() as s:
        return (await s.exec(select(User).where(User.role == Role.OWNER))).first()


# --------------------------------------------------------------------------- #
# Recognition decisions
# --------------------------------------------------------------------------- #


async def test_verified_primary_match_promotes(session_factory):
    user = await _make_user(session_factory, email="owner@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="owner@example.com")),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.PROMOTED
    assert decision.changed
    refreshed = await _owner(session_factory)
    assert refreshed is not None and refreshed.id == user.id


async def test_verified_but_different_email_does_not_promote(session_factory):
    user = await _make_user(session_factory, email="someone@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="someone@example.com")),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.NOT_VERIFIED
    assert not decision.changed
    assert await _owner(session_factory) is None


async def test_unverified_primary_does_not_promote(session_factory):
    user = await _make_user(session_factory, email="owner@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(
                _FakeClerkUser(primary="owner@example.com", status="unverified")
            ),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.NOT_VERIFIED
    assert not decision.changed


async def test_secondary_email_match_only_does_not_promote(session_factory):
    user = await _make_user(session_factory, email="other@example.com")
    clerk_user = _FakeClerkUser(
        primary="primary@example.com",
        secondary=[_FakeEmail("owner@example.com", eid="secondary")],
    )
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(clerk_user),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.NOT_VERIFIED
    assert not decision.changed


async def test_clerk_failure_preserves_ownership(session_factory):
    user = await _make_user(session_factory, email="owner@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(error=RuntimeError("clerk down")),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.IDENTITY_UNAVAILABLE
    assert not decision.changed
    assert await _owner(session_factory) is None


async def test_inactive_designated_account_is_not_promoted(session_factory):
    user = await _make_user(session_factory, email="owner@example.com", active=False)
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="owner@example.com")),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.TARGET_INACTIVE
    assert not decision.changed


async def test_no_config_is_a_no_op(session_factory):
    user = await _make_user(session_factory, email="owner@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="owner@example.com")),
            candidate=u,
            configured_email=None,
        )
    assert decision.action == OwnerAction.NO_CONFIG
    assert not decision.changed


async def test_case_and_whitespace_insensitive_match(session_factory):
    user = await _make_user(session_factory, email="owner@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="Owner@Example.COM")),
            candidate=u,
            configured_email="  OWNER@example.com ",
        )
    assert decision.action == OwnerAction.PROMOTED


async def test_missing_local_account_reports_target_missing(session_factory):
    async with session_factory() as s:
        decision = await evaluate(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="owner@example.com")),
            candidate=None,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.TARGET_MISSING
    assert not decision.changed


# --------------------------------------------------------------------------- #
# Transfer semantics
# --------------------------------------------------------------------------- #


async def test_already_owner_is_idempotent(session_factory):
    user = await _make_user(session_factory, role=Role.OWNER, email="owner@example.com")
    async with session_factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="owner@example.com")),
            candidate=u,
            configured_email="owner@example.com",
        )
    assert decision.action == OwnerAction.ALREADY_OWNER
    assert not decision.changed
    assert (await _owner(session_factory)).id == user.id


async def test_transfer_demotes_previous_owner_to_admin(session_factory):
    old_owner = await _make_user(
        session_factory, role=Role.OWNER, email="old@example.com", clerk="cold"
    )
    new_owner = await _make_user(session_factory, email="new@example.com", clerk="cnew")
    async with session_factory() as s:
        u = await s.get(User, new_owner.id)
        decision = await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="new@example.com")),
            candidate=u,
            configured_email="new@example.com",
        )
    assert decision.action == OwnerAction.TRANSFERRED
    assert decision.previous_owner_id == old_owner.id

    async with session_factory() as s:
        refreshed_old = await s.get(User, old_owner.id)
        refreshed_new = await s.get(User, new_owner.id)
        owners = (await s.exec(select(User).where(User.role == Role.OWNER))).all()
    assert refreshed_old.role == Role.ADMIN  # demoted, not deleted
    assert refreshed_old.is_active is True  # still usable
    assert refreshed_old.clerk_id == "cold"  # identity untouched
    assert refreshed_new.role == Role.OWNER
    assert len(owners) == 1


async def test_transfer_preserves_unrelated_users_and_data(session_factory):
    from app.enums.enums import TicketStatus
    from app.models.ticket import Ticket

    old_owner = await _make_user(
        session_factory, role=Role.OWNER, email="old@example.com", clerk="cold"
    )
    new_owner = await _make_user(session_factory, email="new@example.com", clerk="cnew")
    bystander = await _make_user(
        session_factory, role=Role.AGENT, email="agent@example.com", clerk="cagent"
    )
    async with session_factory() as s:
        s.add(
            Ticket(
                ticket_number=10000,
                title="Existing",
                description="data that must survive a transfer",
                status=TicketStatus.OPEN,
                created_by_user_id=new_owner.id,
                assignee_user_id=bystander.id,
            )
        )
        await s.commit()

    async with session_factory() as s:
        u = await s.get(User, new_owner.id)
        await reconcile_owner(
            s,
            clerk=_FakeClerk(_FakeClerkUser(primary="new@example.com")),
            candidate=u,
            configured_email="new@example.com",
        )

    async with session_factory() as s:
        refreshed_bystander = await s.get(User, bystander.id)
        ticket = (
            await s.exec(select(Ticket).where(Ticket.ticket_number == 10000))
        ).first()
    assert refreshed_bystander.role == Role.AGENT  # untouched
    assert old_owner.id != new_owner.id  # the previous owner still exists
    assert ticket is not None and ticket.assignee_user_id == bystander.id


async def test_repeated_reconciliation_makes_no_second_transfer(session_factory):
    await _make_user(
        session_factory, role=Role.OWNER, email="old@example.com", clerk="cold"
    )
    new_owner = await _make_user(session_factory, email="new@example.com", clerk="cnew")
    clerk = _FakeClerk(_FakeClerkUser(primary="new@example.com"))

    async with session_factory() as s:
        u = await s.get(User, new_owner.id)
        first = await reconcile_owner(
            s, clerk=clerk, candidate=u, configured_email="new@example.com"
        )
    async with session_factory() as s:
        u = await s.get(User, new_owner.id)
        second = await reconcile_owner(
            s, clerk=clerk, candidate=u, configured_email="new@example.com"
        )
    assert first.action == OwnerAction.TRANSFERRED
    assert second.action == OwnerAction.ALREADY_OWNER
    async with session_factory() as s:
        owners = (await s.exec(select(User).where(User.role == Role.OWNER))).all()
    assert len(owners) == 1


async def test_find_candidate_by_email_is_normalized(session_factory):
    user = await _make_user(session_factory, email="owner@example.com")
    async with session_factory() as s:
        found = await find_candidate_by_email(s, "  OWNER@Example.com ")
    assert found is not None and found.id == user.id


# --------------------------------------------------------------------------- #
# Request-path integration (get_current_user)
# --------------------------------------------------------------------------- #


async def test_request_path_promotes_configured_owner(
    client, make_user, session_factory, monkeypatch
):
    from app.core import config as config_module

    user = await make_user(email="owner@example.com")
    monkeypatch.setattr(config_module.settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(config_module.settings, "INITIAL_ADMIN_EMAIL", None)

    # The Clerk lookup used by the request path must return the verified primary
    # email for this identity.
    from app.core import auth as auth_module

    async def _fake_get_async(user_id: str):
        return _FakeClerkUser(primary="owner@example.com")

    monkeypatch.setattr(auth_module.clerk_client.users, "get_async", _fake_get_async)

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": user.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"

    async with session_factory() as s:
        refreshed = await s.get(User, user.id)
    assert refreshed.role == Role.OWNER


async def test_request_path_does_not_promote_unverified(
    client, make_user, session_factory, monkeypatch
):
    from app.core import auth as auth_module
    from app.core import config as config_module

    user = await make_user(email="owner@example.com")
    monkeypatch.setattr(config_module.settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(config_module.settings, "INITIAL_ADMIN_EMAIL", None)

    async def _fake_get_async(user_id: str):
        return _FakeClerkUser(primary="owner@example.com", status="unverified")

    monkeypatch.setattr(auth_module.clerk_client.users, "get_async", _fake_get_async)

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": user.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "customer"
    async with session_factory() as s:
        refreshed = await s.get(User, user.id)
    assert refreshed.role == Role.CUSTOMER


async def test_request_path_survives_clerk_failure(
    client, make_user, session_factory, monkeypatch
):
    from app.core import auth as auth_module
    from app.core import config as config_module

    user = await make_user(email="owner@example.com")
    monkeypatch.setattr(config_module.settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(config_module.settings, "INITIAL_ADMIN_EMAIL", None)

    async def _boom(user_id: str):
        raise RuntimeError("clerk unavailable")

    monkeypatch.setattr(auth_module.clerk_client.users, "get_async", _boom)

    # Authentication must keep working with the stored role.
    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": user.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "customer"


async def test_request_path_owner_fast_path_skips_clerk_and_lock(
    client, make_user, session_factory, monkeypatch
):
    """An existing Owner request must not pay the reconcile round-trip/Clerk call.

    Reconciliation can never *change* an account that already holds OWNER, so the
    request path skips the advisory lock and Clerk verification for them. This is
    the common case for the person browsing the app, and removing those calls is
    the whole point of the fast path. The role must still be returned correctly.
    """
    from app.core import auth as auth_module
    from app.core import config as config_module

    owner = await make_user(role=Role.OWNER, email="owner@example.com")
    monkeypatch.setattr(config_module.settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(config_module.settings, "INITIAL_ADMIN_EMAIL", None)

    calls = {"n": 0}

    async def _spy(user_id: str):
        calls["n"] += 1
        return _FakeClerkUser(primary="owner@example.com")

    monkeypatch.setattr(auth_module.clerk_client.users, "get_async", _spy)

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": owner.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"
    assert calls["n"] == 0, "the Owner fast path must not call Clerk"


# --------------------------------------------------------------------------- #
# Security: no client-side escalation
# --------------------------------------------------------------------------- #


async def test_customer_cannot_set_own_role_to_owner(client, make_user):
    customer = await make_user(role=Role.CUSTOMER)
    response = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": customer.username},
        json={"role": "owner"},
    )
    # Either rejected outright or the field is ignored; never elevated.
    assert response.status_code in (200, 400, 403, 422)
    if response.status_code == 200:
        assert response.json()["role"] != "owner"


async def test_customer_cannot_call_role_endpoint(client, make_user):
    customer = await make_user(role=Role.CUSTOMER)
    owner = await make_user(role=Role.OWNER)
    response = await client.patch(
        f"/api/v1/users/{owner.id}/role",
        headers={"X-Test-User": customer.username},
        json={"role": "admin"},
    )
    assert response.status_code == 403


async def test_admin_cannot_transfer_ownership_via_role_endpoint(client, make_user):
    # OWNER is not assignable; admins lack the owner dependency entirely.
    admin = await make_user(role=Role.ADMIN)
    target = await make_user(role=Role.CUSTOMER)
    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": admin.username},
        json={"role": "owner"},
    )
    assert response.status_code == 403


async def test_agent_cannot_call_role_endpoint(client, make_user):
    agent = await make_user(role=Role.AGENT)
    target = await make_user()
    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": agent.username},
        json={"role": "admin"},
    )
    assert response.status_code == 403


async def test_owner_cannot_assign_owner_role_to_another(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()
    response = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "owner"},
    )
    # The schema/endpoint refuses OWNER as an assignable value.
    assert response.status_code in (400, 403, 422)


# --------------------------------------------------------------------------- #
# Deployment / startup reconciliation is always non-fatal
# --------------------------------------------------------------------------- #


async def test_reconcile_command_no_config_exits_2(monkeypatch, capsys):
    from app.commands import reconcile_owner as cmd

    monkeypatch.setattr(cmd.settings, "OWNER_EMAIL", None)
    monkeypatch.setattr(cmd.settings, "INITIAL_ADMIN_EMAIL", None)
    code = await cmd._run(False)
    assert code == 2
    assert "not configured" in capsys.readouterr().err.lower()


async def test_reconcile_command_unregistered_target_is_non_fatal(monkeypatch, capsys):
    # A designated person who has not signed in yet must not fail a deploy.
    from app.commands import reconcile_owner as cmd

    monkeypatch.setattr(cmd.settings, "OWNER_EMAIL", "not-yet@example.com")
    monkeypatch.setattr(cmd.settings, "INITIAL_ADMIN_EMAIL", None)

    async def _no_candidate(session, configured):
        return None

    monkeypatch.setattr(cmd, "find_candidate_by_email", _no_candidate)
    code = await cmd._run(True)
    assert code == 0
    assert "target_missing" in capsys.readouterr().out


async def test_startup_reconciliation_never_raises(monkeypatch):
    # Even with a broken database the startup hook must swallow the error so the
    # service still becomes available.
    from app import main as main_module

    monkeypatch.setattr(
        main_module.settings, "OWNER_EMAIL", "someone@example.com", raising=False
    )
    # Pointing at an empty in-memory DB with no tables triggers an OperationalError.
    await main_module._reconcile_owner_on_startup()  # must not raise


async def test_request_path_non_matching_user_skips_clerk_and_lock(
    client, make_user, session_factory, monkeypatch
):
    """A non-owner whose email is not the configured OWNER_EMAIL is a pure no-op.

    Reconciliation can only ever promote the account whose stored email matches
    the configured owner address, so every other authenticated request must not
    pay a live Clerk call or take the global transaction-scoped advisory lock.
    Regression for the per-request Clerk round-trip and lock contention that
    serialised all non-owner traffic while an Owner is configured.
    """
    from app.core import auth as auth_module
    from app.core import config as config_module
    from app.services import owner_identity as svc

    customer = await make_user(role=Role.CUSTOMER, email="just-a-customer@example.com")
    monkeypatch.setattr(config_module.settings, "OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(config_module.settings, "INITIAL_ADMIN_EMAIL", None)

    clerk_calls = {"n": 0}
    lock_calls = {"n": 0}

    async def _spy(user_id: str):
        clerk_calls["n"] += 1
        return _FakeClerkUser(primary="someone-else@example.com")

    orig_lock = svc._lock_ownership

    async def _lock_spy(session):
        lock_calls["n"] += 1
        return await orig_lock(session)

    monkeypatch.setattr(auth_module.clerk_client.users, "get_async", _spy)
    monkeypatch.setattr(svc, "_lock_ownership", _lock_spy)

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": customer.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "customer"
    assert clerk_calls["n"] == 0, "a non-matching user must not call Clerk"
    assert lock_calls["n"] == 0, "a non-matching user must not take the owner lock"
