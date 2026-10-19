"""PostgreSQL-only checks for the Owner Inbox internal-message tables.

Skipped unless ``HD_TEST_POSTGRES_URL`` points at a disposable database (the
same guard as ``test_postgres_integration``). SQLite cannot prove these
properties:

* the new native ``internalaudience`` enum and the reused native ``role`` enum
  round-trip through a real write/read cycle;
* the ``(message_id, recipient_user_id)`` unique constraint actually prevents a
  duplicated recipient row in the database, not just in application code.

The database is disposable by contract. To make the audience expansion
deterministic the test deactivates any pre-existing active agent/admin for the
duration of the test (nothing is deleted), and it runs no destructive DDL.
"""

import os
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_auth
from app.core.database import _normalize_database_url, get_db
from app.enums.enums import InternalAudience, Role
from app.main import app
from app.models.internal_message import InternalMessage, InternalMessageRecipient
from app.models.user import User

_PG_URL = os.environ.get("HD_TEST_POSTGRES_URL")
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
async def factory():
    engine = create_async_engine(_normalize_database_url(_PG_URL))
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


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
        username = f"pgim_{uuid.uuid4().hex[:12]}"
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
    """Return the single OWNER, creating it only if none exists yet."""
    async with factory() as session:
        existing = (
            await session.exec(select(User).where(User.role == Role.OWNER))
        ).first()
        if existing is not None:
            return existing

        username = f"pgim_owner_{uuid.uuid4().hex[:8]}"
        owner = User(
            clerk_id=f"test_{username}",
            full_name="Inbox Owner",
            username=username,
            email=f"{username}@example.com",
            role=Role.OWNER,
        )
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        return owner


async def _only_active_staff(factory, keep_ids: set[uuid.UUID]) -> None:
    """Deactivate any other active agent/admin so audience size is exact."""
    async with factory() as session:
        rows = (
            await session.exec(
                select(User).where(
                    User.role.in_([Role.AGENT, Role.ADMIN]),
                    User.is_active.is_(True),
                )
            )
        ).all()
        for user in rows:
            if user.id not in keep_ids:
                user.is_active = False
                session.add(user)
        await session.commit()


@pytest.mark.asyncio
async def test_broadcast_roundtrips_native_enums_and_read_state(
    client, factory, make_user
):
    owner = await _ensure_owner(factory)
    agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    await _only_active_staff(factory, {agent.id, admin.id})

    created = await client.post(
        "/api/v1/internal-messages",
        headers={"X-Test-User": owner.username},
        json={
            "audience": "everyone",
            "subject": "PG roundtrip",
            "body": "Native enum storage.",
        },
    )
    assert created.status_code == 201
    assert created.json()["recipient_count"] == 2
    message_id = uuid.UUID(created.json()["id"])

    async with factory() as session:
        message = await session.get(InternalMessage, message_id)
        rows = (
            await session.exec(
                select(InternalMessageRecipient).where(
                    InternalMessageRecipient.message_id == message_id
                )
            )
        ).all()

    assert message.audience is InternalAudience.EVERYONE
    assert {row.recipient_role_snapshot for row in rows} == {
        Role.AGENT,
        Role.ADMIN,
    }
    assert all(row.read_at is None for row in rows)

    # A recipient reads it through the API; the Sent view then reports it.
    assert (
        await client.post(
            f"/api/v1/internal-messages/{message_id}/read",
            headers={"X-Test-User": agent.username},
        )
    ).json() == {"updated": 1}
    detail = await client.get(
        f"/api/v1/internal-messages/sent/{message_id}",
        headers={"X-Test-User": owner.username},
    )
    assert detail.json()["read_count"] == 1


@pytest.mark.asyncio
async def test_unique_recipient_constraint_is_enforced_by_postgres(
    client, factory, make_user
):
    owner = await _ensure_owner(factory)
    agent = await make_user(role=Role.AGENT)
    await _only_active_staff(factory, {agent.id})

    created = await client.post(
        "/api/v1/internal-messages",
        headers={"X-Test-User": owner.username},
        json={
            "audience": "individual",
            "subject": "One",
            "body": "Only once.",
            "recipient_user_id": str(agent.id),
        },
    )
    assert created.status_code == 201
    message_id = uuid.UUID(created.json()["id"])

    async with factory() as session:
        session.add(
            InternalMessageRecipient(
                message_id=message_id,
                recipient_user_id=agent.id,
                recipient_role_snapshot=Role.AGENT,
                recipient_full_name_snapshot="Duplicate",
                recipient_email_snapshot="dup@example.com",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
