"""Shared pytest fixtures.

The tests run against an in-memory SQLite database (aiosqlite) so they do not
need PostgreSQL or Clerk. Dependencies are overridden:

* ``get_db``          -> a session bound to the test database
* ``get_current_user``-> a fake Clerk identity, selected by the X-Test-User
                         header (the user's username)

This lets us exercise the real routers, schemas and authorization dependencies
without contacting Clerk.
"""

import os
import uuid
from datetime import UTC, datetime

# Provide dummy settings before app modules import them, so the tests do not
# depend on a real .env file or real credentials.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("CLERK_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_auth
from app.core.database import get_db
from app.enums.enums import AttachmentScanStatus, Role, TicketPriority, TicketStatus
from app.main import app
from app.models.ticket import Ticket
from app.models.user import User
from app.services.malware_scan import ScanResult, get_malware_scanner


class CleanTestScanner:
    """Deterministic test-only scanner.

    Production never falls back to this: it is installed only through FastAPI
    dependency overrides in this test harness.
    """

    async def scan(self, path):
        return ScanResult(status=AttachmentScanStatus.CLEAN)


class FakeRequestState:
    """Minimal stand-in for Clerk's RequestState."""

    def __init__(self, clerk_id: str) -> None:
        self.payload = {"sub": clerk_id}
        self.is_signed_in = True


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Keep uploaded test files inside the pytest temporary directory."""
    from app.core import config

    monkeypatch.setattr(config.settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    yield


@pytest.fixture(autouse=True)
def disable_initial_admin_bootstrap(monkeypatch):
    """Disable the bootstrap administrator unless a test opts in.

    ``.env`` may define ``INITIAL_ADMIN_EMAIL`` for local development, but the
    test suite must be deterministic. Tests that exercise bootstrapping
    override ``settings.INITIAL_ADMIN_EMAIL`` themselves.
    """
    from app.core import config

    monkeypatch.setattr(config.settings, "INITIAL_ADMIN_EMAIL", None)
    yield


@pytest.fixture(autouse=True)
def disable_rate_limiting(monkeypatch):
    """Keep API tests deterministic; rate-limit tests opt in explicitly."""
    from app.core import config

    monkeypatch.setattr(config.settings, "RATE_LIMIT_ENABLED", False)
    yield


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def make_user(session_factory):
    async def _make(
        role: Role = Role.CUSTOMER,
        *,
        username: str | None = None,
        email: str | None = None,
        is_active: bool = True,
    ) -> User:
        username = username or f"user_{uuid.uuid4().hex[:8]}"
        email = email or f"{username}@example.com"
        user = User(
            clerk_id=f"test_{username}",
            full_name=username.title(),
            username=username,
            email=email.lower(),
            role=role,
            is_active=is_active,
        )
        async with session_factory() as session:
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    return _make


@pytest_asyncio.fixture
async def make_ticket(session_factory):
    async def _make(
        owner: User,
        *,
        title: str = "Printer is broken",
        status: TicketStatus = TicketStatus.OPEN,
        priority: TicketPriority = TicketPriority.NORMAL,
        assignee: User | None = None,
    ) -> Ticket:
        from app.services.tickets import next_ticket_number

        async with session_factory() as session:
            ticket = Ticket(
                ticket_number=await next_ticket_number(session),
                title=title,
                description="It stopped working this morning.",
                status=status,
                priority=priority,
                created_by_user_id=owner.id,
                assignee_user_id=assignee.id if assignee else None,
                # Mirror the production invariant: assigned_at is written
                # together with the assignee (and cleared on unassignment), so
                # assignment tests do not fall through to the UUID tie-break.
                assigned_at=datetime.now(UTC) if assignee else None,
            )
            session.add(ticket)
            await session.commit()
            await session.refresh(ticket)
        return ticket

    return _make


def _fake_require_auth(request: Request) -> FakeRequestState:
    username = request.headers.get("X-Test-User")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return FakeRequestState(clerk_id=f"test_{username}")


def _install_overrides(session_factory) -> None:
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_auth] = _fake_require_auth
    app.dependency_overrides[get_malware_scanner] = lambda: CleanTestScanner()


@pytest_asyncio.fixture
async def client(session_factory):
    _install_overrides(session_factory)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_raise(session_factory):
    """Like ``client`` but returns the 500 response instead of re-raising.

    Needed for tests that deliberately trigger an unhandled server error.
    """
    _install_overrides(session_factory)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

    app.dependency_overrides.clear()
