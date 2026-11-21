"""End-to-end support flow on a disposable PostgreSQL database.

Covers the core product path in one place:

    authenticate -> create a ticket -> automatic assignment -> agent claims /
    assignee can act on the ticket.

Authentication is the application's real Clerk dependency *contract* but is
driven by the test identity header, exactly like the other PostgreSQL suites:
that keeps production auth untouched while still exercising the real router,
authorization dependencies, database constraints, and assignment service.

Skipped unless ``HD_TEST_POSTGRES_URL`` points at a disposable database whose
name contains ``test``, ``verify`` or ``ci``. It never runs against a real
database and never truncates existing data.
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_auth
from app.core.database import _normalize_database_url, get_db
from app.enums.enums import Role
from app.main import app
from app.models import Ticket, User  # noqa: F401  (register every table)
from tests._disposable_db_guard import is_disposable

_PG_URL = __import__("os").environ.get("HD_TEST_POSTGRES_URL")
# The safety check inspects the database *name*, never the whole URL: a
# production URL can contain "ci" in a username/password/host.

_SAFE = is_disposable(_PG_URL)

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
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
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
        username = f"pge2e_{uuid.uuid4().hex[:12]}"
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


async def _deactivate_pre_existing_agents(factory, keep_ids: set[uuid.UUID]) -> None:
    """Make only this test's agents eligible; never deletes anything."""
    async with factory() as session:
        agents = (
            await session.exec(
                select(User).where(User.role == Role.AGENT, User.is_active.is_(True))
            )
        ).all()
        for agent in agents:
            if agent.id not in keep_ids:
                agent.is_active = False
                session.add(agent)
        await session.commit()


@pytest.mark.asyncio
async def test_authenticated_customer_can_create_and_assign_a_ticket(
    client, factory, make_user
):
    # 1. Authentication: an unknown identity is rejected (401) — no profile is
    #    provisioned because there is no session.
    unauthenticated = await client.get("/api/v1/users/me")
    assert unauthenticated.status_code == 401

    # 2. A signed-in customer is provisioned and can load their profile.
    customer = await make_user()
    me = await client.get(
        "/api/v1/users/me", headers={"X-Test-User": customer.username}
    )
    assert me.status_code == 200
    assert me.json()["id"] == str(customer.id)
    assert me.json()["role"] == "customer"

    # 3. One eligible agent so assignment is deterministic.
    agent = await make_user(role=Role.AGENT)
    await _deactivate_pre_existing_agents(factory, {agent.id})

    # 4. The customer opens a ticket; it is auto-assigned to the only agent.
    created = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "VPN will not connect",
            "description": "The client fails during the handshake.",
            "category": "TECHNICAL",
            "impact": "HIGH",
        },
    )
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["assignee_user_id"] == str(agent.id)
    assert ticket["status"] == "OPEN"
    assert ticket["priority"] == "HIGH"

    # 5. Assignment is enforced authoritatively: the assigned agent sees the
    #    ticket, an unrelated customer does not.
    agent_view = await client.get(
        f"/api/v1/tickets/{ticket['id']}",
        headers={"X-Test-User": agent.username},
    )
    assert agent_view.status_code == 200
    assert agent_view.json()["assignee_user_id"] == str(agent.id)

    other_customer = await make_user()
    forbidden = await client.get(
        f"/api/v1/tickets/{ticket['id']}",
        headers={"X-Test-User": other_customer.username},
    )
    assert forbidden.status_code == 404

    # 6. The agent moves the ticket forward, which is a real staff action.
    updated = await client.patch(
        f"/api/v1/tickets/{ticket['id']}",
        headers={"X-Test-User": agent.username},
        json={"status": "IN_PROGRESS"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "IN_PROGRESS"


@pytest.mark.asyncio
async def test_agent_queue_claim_flow(client, factory, make_user):
    """An unassigned ticket can be claimed exactly once by an agent."""
    # No eligible agents -> the ticket stays in the unassigned queue.
    await _deactivate_pre_existing_agents(factory, set())

    customer = await make_user()
    created = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Need a laptop",
            "description": "Replacement hardware request.",
            "category": "TECHNICAL",
        },
    )
    assert created.status_code == 201
    ticket = created.json()
    assert ticket["assignee_user_id"] is None

    agent = await make_user(role=Role.AGENT)
    await _deactivate_pre_existing_agents(factory, {agent.id})

    claim = await client.post(
        f"/api/v1/tickets/{ticket['id']}/claim",
        headers={"X-Test-User": agent.username},
    )
    assert claim.status_code == 200
    assert claim.json()["assignee_user_id"] == str(agent.id)

    # Re-claiming an already-assigned ticket is a clean conflict (409), not a
    # second assignment. The ticket is still visible to the same agent.
    reclaim = await client.post(
        f"/api/v1/tickets/{ticket['id']}/claim",
        headers={"X-Test-User": agent.username},
    )
    assert reclaim.status_code == 409

    # A different agent cannot even see the ticket once it is assigned to
    # someone else: the API returns 404 rather than revealing its existence.
    second_agent = await make_user(role=Role.AGENT)
    await _deactivate_pre_existing_agents(factory, {agent.id, second_agent.id})
    other_agent_claim = await client.post(
        f"/api/v1/tickets/{ticket['id']}/claim",
        headers={"X-Test-User": second_agent.username},
    )
    assert other_agent_claim.status_code == 404
