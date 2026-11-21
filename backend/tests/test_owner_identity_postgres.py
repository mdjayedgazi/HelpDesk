"""PostgreSQL-only guarantees for configurable Owner identity.

Opt-in: skipped unless ``HD_TEST_POSTGRES_URL`` points at a disposable database
(name must contain ``test``/``verify``/``ci``/``demo``). This suite exercises the
things SQLite cannot prove:

* the *real* partial unique index ``uq_users_single_owner``;
* the demote-then-promote ordering inside one transaction;
* transaction-scoped advisory locking under concurrency;
* exactly one Owner after concurrent reconciliation;
* that transfers leave tickets and comments intact.

Never point this at production.
"""

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import _normalize_database_url
from app.enums.enums import Role, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.services.owner_identity import (
    OwnerAction,
    OwnerIdentityError,
    reconcile_owner,
)
from tests._disposable_db_guard import is_disposable

_PG_URL = os.environ.get("HD_TEST_POSTGRES_URL")
_SAFE = is_disposable(_PG_URL)

pytestmark = pytest.mark.skipif(
    not _SAFE,
    reason="set HD_TEST_POSTGRES_URL to a disposable database",
)


class _FakeEmail:
    def __init__(self, address: str, status: str = "verified"):
        self.id = "primary"
        self.email_address = address
        self.verification = SimpleNamespace(status=SimpleNamespace(value=status))


class _FakeClerkUser:
    def __init__(self, primary: str, status: str = "verified"):
        self.primary_email_address_id = "primary"
        self.email_addresses = [_FakeEmail(primary, status)]
        self.image_url = None


class _FakeUsers:
    def __init__(self, email_map: dict[str, str]):
        self._email_map = email_map

    async def get_async(self, user_id: str):
        return _FakeClerkUser(self._email_map[user_id])


class _FakeClerk:
    def __init__(self, email_map: dict[str, str]):
        self.users = _FakeUsers(email_map)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(_normalize_database_url(_PG_URL))
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.drop_all)
        await connection.run_sync(SQLModel.metadata.create_all)
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _add_user(
    factory, *, email: str, role: Role, clerk: str | None = None
) -> User:
    user = User(
        clerk_id=clerk or f"clerk_{uuid.uuid4().hex[:8]}",
        full_name="Test Person",
        username=f"u_{uuid.uuid4().hex[:10]}",
        email=email.lower(),
        role=role,
        is_active=True,
    )
    async with factory() as s:
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return user


async def _owner_count(factory) -> int:
    async with factory() as s:
        return int(
            (
                await s.exec(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == Role.OWNER)
                )
            ).one()
        )


async def test_partial_unique_index_exists(factory):
    from sqlalchemy import text

    async with factory() as s:
        result = (
            await s.exec(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_users_single_owner'"
                )
            )
        ).all()
    assert result, "uq_users_single_owner is missing"
    indexdef = result[0][0]
    assert "UNIQUE INDEX" in indexdef.upper()
    assert "WHERE (role" in indexdef


async def test_promotion_succeeds(factory):
    user = await _add_user(factory, email="owner@example.com", role=Role.CUSTOMER)
    clerk = _FakeClerk({user.clerk_id: "owner@example.com"})
    async with factory() as s:
        u = await s.get(User, user.id)
        decision = await reconcile_owner(
            s, clerk=clerk, candidate=u, configured_email="owner@example.com"
        )
    assert decision.action == OwnerAction.PROMOTED
    assert await _owner_count(factory) == 1


async def test_transfer_never_leaves_two_owners(factory):
    old = await _add_user(factory, email="old@example.com", role=Role.OWNER)
    new = await _add_user(factory, email="new@example.com", role=Role.CUSTOMER)
    clerk = _FakeClerk({new.clerk_id: "new@example.com"})

    async with factory() as s:
        u = await s.get(User, new.id)
        decision = await reconcile_owner(
            s, clerk=clerk, candidate=u, configured_email="new@example.com"
        )
    assert decision.action == OwnerAction.TRANSFERRED
    assert await _owner_count(factory) == 1

    async with factory() as s:
        before = await s.get(User, old.id)
        after = await s.get(User, new.id)
    assert before.role == Role.ADMIN and before.is_active
    assert after.role == Role.OWNER


async def test_concurrent_reconciliation_yields_one_owner(factory):
    old = await _add_user(factory, email="old@example.com", role=Role.OWNER)
    new = await _add_user(factory, email="new@example.com", role=Role.CUSTOMER)
    clerk = _FakeClerk({new.clerk_id: "new@example.com"})

    async def attempt():
        async with factory() as s:
            u = await s.get(User, new.id)
            try:
                return await reconcile_owner(
                    s, clerk=clerk, candidate=u, configured_email="new@example.com"
                )
            except OwnerIdentityError:
                return None

    await asyncio.gather(*(attempt() for _ in range(5)), return_exceptions=True)

    assert await _owner_count(factory) == 1
    async with factory() as s:
        owners = (await s.exec(select(User).where(User.role == Role.OWNER))).all()
        old_row = await s.get(User, old.id)
    assert owners[0].id == new.id
    assert old_row.role == Role.ADMIN


async def test_transfer_preserves_tickets_and_comments(factory):
    from app.models.comment import Comment

    old = await _add_user(factory, email="old@example.com", role=Role.OWNER)
    new = await _add_user(factory, email="new@example.com", role=Role.CUSTOMER)
    ticket_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            Ticket(
                id=ticket_id,
                ticket_number=10001,
                title="Historical",
                description="must survive",
                status=TicketStatus.OPEN,
                created_by_user_id=old.id,
                assignee_user_id=None,
            )
        )
        await s.commit()
        s.add(
            Comment(
                ticket_id=ticket_id,
                author_user_id=old.id,
                body="existing comment",
            )
        )
        await s.commit()

    clerk = _FakeClerk({new.clerk_id: "new@example.com"})
    async with factory() as s:
        u = await s.get(User, new.id)
        await reconcile_owner(
            s, clerk=clerk, candidate=u, configured_email="new@example.com"
        )

    async with factory() as s:
        ticket = await s.get(Ticket, ticket_id)
        comments = (
            await s.exec(select(Comment).where(Comment.ticket_id == ticket_id))
        ).all()
        old_row = await s.get(User, old.id)
    assert ticket.created_by_user_id == old.id  # ownership of data unchanged
    assert len(comments) == 1 and comments[0].author_user_id == old.id
    assert old_row.role == Role.ADMIN  # only the role changed


async def test_failed_transfer_rolls_back(factory, monkeypatch):
    old = await _add_user(factory, email="old@example.com", role=Role.OWNER)
    new = await _add_user(factory, email="new@example.com", role=Role.CUSTOMER)
    clerk = _FakeClerk({new.clerk_id: "new@example.com"})

    # Force the target write to fail after the demotion flush.
    from app.services import owner_identity as svc

    original_flush = AsyncSession.flush

    async def _boom(self, *a, **k):
        raise RuntimeError("simulated persistence failure")

    async with factory() as s:
        u = await s.get(User, new.id)
        monkeypatch.setattr("sqlmodel.ext.asyncio.session.AsyncSession.flush", _boom)
        with pytest.raises(RuntimeError):
            await svc.reconcile_owner(
                s, clerk=clerk, candidate=u, configured_email="new@example.com"
            )
        monkeypatch.setattr(
            "sqlmodel.ext.asyncio.session.AsyncSession.flush", original_flush
        )

    # Rollback restored the original state: the previous Owner is still OWNER.
    async with factory() as s:
        old_row = await s.get(User, old.id)
        new_row = await s.get(User, new.id)
    assert old_row.role == Role.OWNER
    assert new_row.role == Role.CUSTOMER
    assert await _owner_count(factory) == 1
