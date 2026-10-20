"""PostgreSQL-only tests for concurrency behavior of the new workflows.

Skipped unless ``HD_TEST_POSTGRES_URL`` points at a disposable database (the
same guard as ``test_postgres_integration``). SQLite serialises writers and
ignores row locks, so these properties can only be proven on PostgreSQL:

* concurrent intake: the advisory lock serialises assignment decisions, so six
  simultaneous tickets are spread 2/2/2 across three agents instead of
  hot-spotting one of them from stale workload snapshots;
* concurrent claim: the ticket row lock means two agents racing for the same
  unassigned ticket cannot both succeed.

The database is disposable by contract. To isolate the workload experiments,
any AGENT account that already exists in it is deactivated for the duration of
the test (fresh accounts are created for each assertion), and the module runs
no destructive DDL.
"""

import asyncio
import itertools
import os
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routers import tickets as tickets_router
from app.core.auth import require_auth
from app.core.database import _normalize_database_url, get_db
from app.enums.enums import NotificationType, Role, TicketPriority
from app.main import app
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory
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
        username = f"pgwf_{uuid.uuid4().hex[:12]}"
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

    The partial unique index ``uq_users_single_owner`` permits exactly one
    OWNER row, and the disposable database is shared across the PostgreSQL
    test modules, so the test reuses whatever Owner already exists.
    """
    async with factory() as session:
        existing = (
            await session.exec(select(User).where(User.role == Role.OWNER))
        ).first()
        if existing is not None:
            return existing

        username = f"pgwf_owner_{uuid.uuid4().hex[:8]}"
        owner = User(
            clerk_id=f"test_{username}",
            full_name="Workflow Owner",
            username=username,
            email=f"{username}@example.com",
            role=Role.OWNER,
        )
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        return owner


async def _deactivate_pre_existing_agents(factory, keep_ids: set[uuid.UUID]) -> None:
    """Keep only the workload agents of this test eligible.

    The disposable database is shared with the other PostgreSQL modules, which
    may have left active agents behind. Deactivating them is confined to this
    throwaway database; nothing is deleted.
    """
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
async def test_concurrent_intake_balances_assignment(
    client, factory, make_user, monkeypatch
):
    agents = [await make_user(role=Role.AGENT) for _ in range(3)]
    await _deactivate_pre_existing_agents(factory, {a.id for a in agents})

    customer = await make_user()

    # Give every concurrent request a distinct ticket number atomically;
    # ticket-number allocation is covered elsewhere, this test is about the
    # assignment decision under concurrency.
    async with factory() as session:
        current_max = (await session.exec(select(Ticket.ticket_number))).all()
    numbers = itertools.count(max(n for n in current_max if n is not None) + 1)

    async def fake_next_ticket_number(session):
        return next(numbers)

    monkeypatch.setattr(tickets_router, "next_ticket_number", fake_next_ticket_number)

    async def create(index: int):
        return await client.post(
            "/api/v1/tickets",
            headers={"X-Test-User": customer.username},
            json={
                "title": f"Concurrent ticket {index}",
                "description": "Created concurrently.",
                "category": "TECHNICAL",
            },
        )

    responses = await asyncio.gather(*(create(i) for i in range(6)))
    assert [r.status_code for r in responses] == [201] * 6

    assigned_ids = [r.json()["assignee_user_id"] for r in responses]
    assert set(assigned_ids) == {str(a.id) for a in agents}

    counts = {str(a.id): assigned_ids.count(str(a.id)) for a in agents}
    # 6 tickets, 3 equally loaded agents, serialised decisions: exactly 2 each.
    assert sorted(counts.values()) == [2, 2, 2], counts

    # Every assignment of this test's tickets is auditable with its reason.
    ticket_ids = [uuid.UUID(r.json()["id"]) for r in responses]
    async with factory() as session:
        history = (
            await session.exec(
                select(TicketHistory).where(
                    TicketHistory.event_type == "TICKET_ASSIGNED",
                    TicketHistory.ticket_id.in_(ticket_ids),
                )
            )
        ).all()
    assert len(history) == 6
    reasons = {row.new_value["reason"] for row in history if row.new_value is not None}
    assert reasons <= {
        "LEAST_LOADED",
        "FAIR_ROTATION",
        "RECENT_RESOLUTION_SPEED",
        "STABLE_ROTATION",
        "ONLY_ELIGIBLE_AGENT",
    }


@pytest.mark.asyncio
async def test_concurrent_claim_has_exactly_one_winner(client, factory, make_user):
    agents = [await make_user(role=Role.AGENT) for _ in range(2)]
    await _deactivate_pre_existing_agents(factory, {a.id for a in agents})
    customer = await make_user()

    created = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Claim race",
            "description": "Two agents want this one.",
            "category": "TECHNICAL",
        },
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]
    # The ticket may have been auto-assigned; unassign it through the API to
    # create the queue state the race needs.
    # (An admin is not required: the auto-assignment is exactly what we undo.)
    async with factory() as session:
        ticket = await session.get(Ticket, uuid.UUID(ticket_id))
        ticket.assignee_user_id = None
        ticket.assigned_at = None
        session.add(ticket)
        await session.commit()

    async def claim(agent):
        return await client.post(
            f"/api/v1/tickets/{ticket_id}/claim",
            headers={"X-Test-User": agent.username},
        )

    first, second = await asyncio.gather(*(claim(a) for a in agents))
    statuses = sorted([first.status_code, second.status_code])
    # Exactly one claim wins; the loser is told the ticket is already assigned
    # (409 if it was assigned to them, 404 otherwise - never a second 200).
    assert statuses[0] == 200
    assert statuses[1] in (404, 409)

    winner = first if first.status_code == 200 else second
    winner_id = winner.json()["assignee_user_id"]

    async with factory() as session:
        stored = await session.get(Ticket, uuid.UUID(ticket_id))
        history = (
            await session.exec(
                select(TicketHistory).where(
                    TicketHistory.ticket_id == uuid.UUID(ticket_id),
                    TicketHistory.event_type == "TICKET_ASSIGNED",
                )
            )
        ).all()
    assert str(stored.assignee_user_id) == winner_id
    # The intake auto-assignment already wrote one row; the loser of the race
    # must not have written anything, so exactly one claim row exists.
    claim_rows = [
        row
        for row in history
        if row.new_value is not None and row.new_value.get("reason") == "AGENT_CLAIMED"
    ]
    assert len(claim_rows) == 1


@pytest.mark.asyncio
async def test_new_workflow_enums_roundtrip_on_postgres(client, factory, make_user):
    """Native enum columns for the new workflows survive a write/read cycle."""
    from app.models.account_request import AccountManagementRequest
    from app.models.staff_message import StaffConversation, StaffMessage

    owner = await _ensure_owner(factory)
    agent = await make_user(role=Role.AGENT)
    # Make the fresh agent the only eligible assignee so the intake below is
    # deterministically routed to them and they can view the ticket when
    # raising the escalation.
    await _deactivate_pre_existing_agents(factory, {agent.id})
    customer = await make_user()

    intake = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json={
            "title": "Enum roundtrip",
            "description": "Native enum storage.",
            "category": "OUTAGE",
            "impact": "CRITICAL",
            "contact_phone": "+1 555 010 4242",
        },
    )
    assert intake.status_code == 201
    ticket_id = uuid.UUID(intake.json()["id"])
    assert intake.json()["category"] == "OUTAGE"
    assert intake.json()["priority"] == TicketPriority.URGENT.value
    assert "contact_phone" not in intake.json()

    escalation = await client.post(
        "/api/v1/account-requests",
        headers={"X-Test-User": agent.username},
        json={
            "category": "IDENTITY_LINKING",
            "justification": "Roundtrip test.",
            "ticket_id": str(ticket_id),
        },
    )
    assert escalation.status_code == 201
    request_id = uuid.UUID(escalation.json()["id"])

    conversation_id = (
        await client.post(
            "/api/v1/staff-messages/conversations",
            headers={"X-Test-User": agent.username},
            json={"subject": "Roundtrip"},
        )
    ).json()["id"]
    sent = await client.post(
        f"/api/v1/staff-messages/conversations/{conversation_id}/messages",
        headers={"X-Test-User": agent.username},
        json={"body": "Native roundtrip."},
    )
    assert sent.status_code == 201

    async with factory() as session:
        stored_ticket = await session.get(Ticket, ticket_id)
        stored_request = await session.get(AccountManagementRequest, request_id)
        stored_conversation = await session.get(
            StaffConversation, uuid.UUID(conversation_id)
        )
        messages = (
            await session.exec(
                select(StaffMessage).where(
                    StaffMessage.conversation_id == uuid.UUID(conversation_id)
                )
            )
        ).all()
        notifications = (
            await session.exec(
                select(Notification).where(
                    Notification.related_conversation_id == uuid.UUID(conversation_id),
                    Notification.type == NotificationType.STAFF_MESSAGE_RECEIVED,
                )
            )
        ).all()

    assert stored_ticket.category.value == "OUTAGE"
    assert stored_ticket.contact_phone == "+1 555 010 4242"
    assert stored_request.category.value == "IDENTITY_LINKING"
    assert stored_request.status.value == "PENDING"
    assert stored_conversation.owner_user_id == owner.id
    assert len(messages) == 1 and messages[0].body == "Native roundtrip."
    assert len(notifications) == 1
    assert notifications[0].recipient_user_id == owner.id
