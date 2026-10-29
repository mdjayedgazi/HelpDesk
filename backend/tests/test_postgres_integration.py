"""Opt-in integration tests against a real PostgreSQL database.

These tests are skipped unless ``HD_TEST_POSTGRES_URL`` is set and points at a
*disposable* database whose name contains ``test``, ``verify`` or ``ci``. They
cover the behavior that SQLite cannot: native PostgreSQL enum types, real
unique / foreign-key / check constraint enforcement, and the psycopg SQLSTATE
branch of the ticket-number collision handling.

Safety: the tests only create missing tables and insert rows with unique
usernames/emails. They never truncate or drop existing data.

Run against a throwaway database, for example:

    docker run --rm -d --name hd_pg -e POSTGRES_PASSWORD=verify \\
        -e POSTGRES_USER=verify -e POSTGRES_DB=hdverify \\
        -p 127.0.0.1:55432:5432 postgres:18-alpine
    cd backend
    HD_TEST_POSTGRES_URL='postgresql+psycopg://verify:verify@127.0.0.1:55432/hdverify' \\
        .venv/bin/python -m pytest tests/test_postgres_integration.py -q
"""

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_auth
from app.core.database import _normalize_database_url, get_db
from app.enums.enums import Role, TicketPriority, TicketStatus
from app.main import app
from app.models import (  # noqa: F401  (registers every table on metadata)
    Attachment,
    Comment,
    Notification,
    Ticket,
    TicketHistory,
    User,
)

_PG_URL = os.environ.get("HD_TEST_POSTGRES_URL")

# Refuse to run against anything that does not look like a disposable DB.
_SAFE = bool(_PG_URL) and any(
    marker in _PG_URL.lower() for marker in ("test", "verify", "ci")
)

pytestmark = pytest.mark.skipif(
    not _SAFE,
    reason="set HD_TEST_POSTGRES_URL to a disposable PostgreSQL database to run",
)


class _FakeState:
    def __init__(self, clerk_id: str) -> None:
        self.payload = {"sub": clerk_id}
        self.is_signed_in = True


def _fake_require_auth(request: Request) -> _FakeState:
    username = request.headers.get("X-Test-User")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return _FakeState(clerk_id=f"test_{username}")


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(_normalize_database_url(_PG_URL))
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def factory(pg_engine):
    return async_sessionmaker(
        bind=pg_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def client(factory):
    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = _fake_require_auth
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def make_user(factory):
    async def _make(role: Role = Role.CUSTOMER, *, is_active: bool = True) -> User:
        username = f"pg_{uuid.uuid4().hex[:12]}"
        user = User(
            clerk_id=f"test_{username}",
            full_name=username.title(),
            username=username,
            email=f"{username}@example.com",
            role=role,
            is_active=is_active,
        )
        async with factory() as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    return _make


async def _ensure_owner(factory) -> User:
    """Return the single OWNER, creating it only if none exists yet.

    The disposable database is shared across the tests in this module and the
    ``uq_users_single_owner`` partial unique index permits exactly one OWNER row
    in total, so every test reuses the same Owner instead of each creating its
    own.
    """
    async with factory() as session:
        existing = (
            await session.exec(select(User).where(User.role == Role.OWNER))
        ).first()
        if existing is not None:
            expected_clerk_id = f"test_{existing.username}"
            if existing.clerk_id == expected_clerk_id:
                return existing
            if not existing.clerk_id:
                # An unlinked Owner row (e.g. left behind by a manual run of
                # the bootstrap command against this disposable database).
                # Link it to the fake test identity so the X-Test-User header
                # resolves to it instead of falling through to Clerk (502).
                existing.clerk_id = expected_clerk_id
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
                return existing
            pytest.skip(
                "the disposable database already has an OWNER linked to a "
                "non-test Clerk identity; use a fresh database"
            )

        username = f"pg_owner_{uuid.uuid4().hex[:8]}"
        owner = User(
            clerk_id=f"test_{username}",
            full_name="Postgres Owner",
            username=username,
            email=f"{username}@example.com",
            role=Role.OWNER,
        )
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        return owner


@pytest_asyncio.fixture
async def owner(factory) -> User:
    """The module's single Owner account (created on first use)."""
    return await _ensure_owner(factory)


@pytest_asyncio.fixture
async def make_ticket(factory):
    async def _make(owner: User, *, assignee: User | None = None) -> Ticket:
        from app.services.tickets import next_ticket_number

        async with factory() as session:
            ticket = Ticket(
                ticket_number=await next_ticket_number(session),
                title="Postgres ticket",
                description="Created by the Postgres integration test.",
                status=TicketStatus.OPEN,
                priority=TicketPriority.NORMAL,
                created_by_user_id=owner.id,
                assignee_user_id=assignee.id if assignee else None,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
        return ticket

    return _make


async def test_metadata_tables_exist(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_postgres_statement_timeout_connect_option_is_applied():
    engine = create_async_engine(
        _normalize_database_url(_PG_URL),
        connect_args={"options": "-c statement_timeout=1234"},
    )
    try:
        async with engine.connect() as connection:
            value = await connection.scalar(text("SHOW statement_timeout"))
        assert value == "1234ms"
    finally:
        await engine.dispose()


async def test_customer_ticket_creation_and_enum_roundtrip(client, make_user):
    customer = await make_user()
    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "PG enum roundtrip",
            "description": "Native enum storage.",
            "category": "BUG",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "OPEN"
    assert body["priority"] == "NORMAL"
    assert body["created_by_user_id"] == str(customer.id)


async def test_ticket_number_collision_retries_using_pg_sqlstate(
    client, make_user, make_ticket, monkeypatch
):
    """Forces a duplicate ticket_number so the psycopg 23505 branch runs."""
    from app.api.routers import tickets as router

    customer = await make_user()
    existing = await make_ticket(customer)

    numbers = iter([existing.ticket_number, existing.ticket_number + 1])

    async def fake_next(session):
        return next(numbers)

    monkeypatch.setattr(router, "next_ticket_number", fake_next)

    response = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Retry on PG",
            "description": "Collides once.",
            "category": "TECHNICAL",
        },
    )
    assert response.status_code == 201
    assert response.json()["ticket_number"] == existing.ticket_number + 1


async def test_history_and_queue_authorization(client, make_user, make_ticket, owner):
    agent = await make_user(Role.AGENT)
    admin = await make_user(Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer, assignee=agent)

    # Customer: no internal history.
    forbidden = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": customer.username},
    )
    assert forbidden.status_code == 403

    # Agent: history allowed for an assigned ticket.
    allowed = await client.get(
        f"/api/v1/tickets/{ticket.id}/history",
        headers={"X-Test-User": agent.username},
    )
    assert allowed.status_code == 200

    # Admin: stays off the agent-only queue endpoint.
    queue = await client.get(
        "/api/v1/tickets/assigned", headers={"X-Test-User": admin.username}
    )
    assert queue.status_code == 403

    # Owner holds administrative capabilities but still gets no agent-only queue.
    owner_queue = await client.get(
        "/api/v1/tickets/assigned", headers={"X-Test-User": owner.username}
    )
    assert owner_queue.status_code == 403


async def test_database_constraints_are_enforced(factory, make_user, make_ticket):
    """Foreign keys, the unique ticket_number index and CHECKs really run."""
    customer = await make_user()
    ticket = await make_ticket(customer)

    # 1. Unique ticket number.
    async with factory() as session:
        session.add(
            Ticket(
                ticket_number=ticket.ticket_number,
                title="Duplicate number",
                description="Should violate the unique index.",
                created_by_user_id=customer.id,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    # 2. Foreign key.
    async with factory() as session:
        session.add(
            Ticket(
                ticket_number=999_999_999,
                title="Bad owner",
                description="Non-existent user id.",
                created_by_user_id=uuid.uuid4(),
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    # 3. CHECK: lowercase email.
    async with factory() as session:
        session.add(
            User(
                full_name="Bad Email",
                username=f"bad_{uuid.uuid4().hex[:8]}",
                email="UPPER@example.com",
                role=Role.CUSTOMER,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    # 4. CHECK: non-negative attachment size.
    async with factory() as session:
        session.add(
            Attachment(
                ticket_id=ticket.id,
                uploaded_by_user_id=customer.id,
                original_filename="x.txt",
                storage_key=uuid.uuid4().hex,
                content_type="text/plain",
                size_bytes=-1,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_owner_user_management_on_real_postgres(
    client, factory, make_user, owner
):
    """Real PostgreSQL: Owner-only role management and the single-Owner index.

    Clerk is not involved: the ``X-Test-User`` dependency override supplies the
    authenticated identity, and everything else (roles, enum storage, the
    partial unique index) is exercised against real PostgreSQL.
    """
    admin = await make_user(Role.ADMIN)
    target = await make_user(Role.CUSTOMER)

    # An ordinary admin cannot manage roles.
    forbidden = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": admin.username},
        json={"role": "agent"},
    )
    assert forbidden.status_code == 403

    # The Owner can.
    allowed = await client.patch(
        f"/api/v1/users/{target.id}/role",
        headers={"X-Test-User": owner.username},
        json={"role": "agent"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["role"] == "agent"

    async with factory() as session:
        refreshed = await session.get(User, target.id)
        assert refreshed is not None
        assert refreshed.role == Role.AGENT

    # The database itself refuses a second OWNER.
    async with factory() as session:
        session.add(
            User(
                clerk_id=f"test_second_{uuid.uuid4().hex[:8]}",
                full_name="Second Owner",
                username=f"second_owner_{uuid.uuid4().hex[:8]}",
                email=f"second_owner_{uuid.uuid4().hex[:8]}@example.com",
                role=Role.OWNER,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_ticket_row_lock_serializes_concurrent_updates(
    factory, make_user, make_ticket
):
    """PostgreSQL really blocks a second FOR UPDATE read until the first commits.

    The API uses this lock for PATCH /tickets/{id}; without it two concurrent
    staff updates could compute history or status transitions from stale data.
    """
    customer = await make_user()
    agent = await make_user(Role.AGENT)
    ticket = await make_ticket(customer, assignee=agent)

    async with factory() as session_a:
        locked = await session_a.get(Ticket, ticket.id, with_for_update=True)
        assert locked is not None

        async def second_reader():
            async with factory() as session_b:
                return await session_b.get(Ticket, ticket.id, with_for_update=True)

        pending = asyncio.create_task(second_reader())
        await asyncio.sleep(0.2)
        assert pending.done() is False

        locked.title = "Updated while holding the lock"
        await session_a.commit()

        observed = await asyncio.wait_for(pending, timeout=5)
        assert observed is not None
        assert observed.title == "Updated while holding the lock"


async def test_owner_enum_roundtrip(client, owner):
    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": owner.username}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "owner"


# --------------------------------------------------------------------------- #
# Lazy provisioning on real PostgreSQL (mocked Clerk)
# --------------------------------------------------------------------------- #


class _FakeEmail:
    def __init__(self, address: str) -> None:
        self.id = "email_1"
        self.email_address = address
        self.verification = SimpleNamespace(status=SimpleNamespace(value="verified"))


class _FakeClerkUser:
    """Mirrors the real SDK: optional ``username`` is present but ``None``."""

    def __init__(self, email: str) -> None:
        self.primary_email_address_id = "email_1"
        self.email_addresses = [_FakeEmail(email)]
        self.username = None
        self.first_name = None
        self.last_name = None


class _FakeClerk:
    def __init__(self, email: str) -> None:
        self._email = email

    @property
    def users(self):
        email = self._email

        async def get_async(user_id: str) -> _FakeClerkUser:
            return _FakeClerkUser(email)

        return SimpleNamespace(get_async=get_async)


async def test_new_signup_provisions_customer_on_real_postgres(
    client, factory, monkeypatch
):
    """The live 500 regression: first ``GET /users/me`` provisions CUSTOMER.

    This drives the real ``get_current_user`` provisioning path against real
    PostgreSQL (Clerk mocked). Before the OWNER enum existed / while a request
    could try to persist OWNER, this request returned HTTP 500; it must return
    200 with a CUSTOMER profile and store the row.
    """
    from app.core import auth

    email = f"pgnew_{uuid.uuid4().hex[:10]}@example.com"
    monkeypatch.setattr(auth, "clerk_client", _FakeClerk(email))

    response = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": f"new_{uuid.uuid4().hex[:8]}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "customer"
    assert body["email"] == email

    async with factory() as session:
        stored = (await session.exec(select(User).where(User.email == email))).first()
        assert stored is not None
        assert stored.role == Role.CUSTOMER
        assert stored.is_active is True
