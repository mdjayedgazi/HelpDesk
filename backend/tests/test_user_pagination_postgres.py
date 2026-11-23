"""PostgreSQL-only checks for the user-directory pagination query.

Skipped unless ``HD_TEST_POSTGRES_URL`` points at a disposable database (the
same guard as the rest of the PostgreSQL suite). SQLite cannot prove that the
``count(*) OVER ()`` window and the ``created_at DESC, id DESC`` ordering behave
exactly as they do in the production database, so this module exercises the real
``_count_and_page_users`` helper against PostgreSQL.

The database is disposable by contract; the tests only create missing tables and
insert rows with unique usernames/emails. Nothing is truncated or dropped.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routers.users import _count_and_page_users
from app.core.database import _normalize_database_url
from app.enums.enums import Role
from app.models.user import User
from tests._disposable_db_guard import is_disposable

_PG_URL = os.environ.get("HD_TEST_POSTGRES_URL")
_SAFE = is_disposable(_PG_URL)

pytestmark = pytest.mark.skipif(
    not _SAFE,
    reason="set HD_TEST_POSTGRES_URL to a disposable PostgreSQL database to run",
)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(_normalize_database_url(_PG_URL))
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _insert(factory, *, created_at: datetime, role: Role = Role.CUSTOMER) -> User:
    username = f"pgp_{uuid.uuid4().hex[:12]}"
    user = User(
        clerk_id=f"test_{username}",
        full_name=username.title(),
        username=username,
        email=f"{username}@example.com",
        role=role,
        is_active=True,
        created_at=created_at,
    )
    async with factory() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_windowed_count_and_page_matches_real_total(factory):
    base = datetime.now(UTC)
    for index in range(5):
        await _insert(factory, created_at=base + timedelta(seconds=index))

    async with factory() as session:
        items, total = await _count_and_page_users(session, [], limit=2, offset=0)
    assert total >= 5
    assert len(items) == 2


@pytest.mark.asyncio
async def test_ordering_is_created_at_then_id_desc(factory):
    base = datetime.now(UTC)
    # Identical created_at forces the id tie-breaker to decide the order.
    same = base
    created = [await _insert(factory, created_at=same) for _ in range(4)]
    expected_ids = {u.id for u in created}

    async with factory() as session:
        items, _total = await _count_and_page_users(
            session,
            [User.id.in_(expected_ids)],
            limit=4,
            offset=0,
        )

    # All four rows come back exactly once, ordered by id DESC within the tie.
    got_ids = [u.id for u in items]
    assert len(got_ids) == 4
    assert set(got_ids) == expected_ids
    assert got_ids == sorted(got_ids, reverse=True)


@pytest.mark.asyncio
async def test_out_of_range_page_returns_true_total(factory):
    base = datetime.now(UTC)
    for index in range(3):
        await _insert(factory, created_at=base + timedelta(seconds=index))

    async with factory() as session:
        items, total = await _count_and_page_users(session, [], limit=2, offset=10_000)
    assert items == []
    # The fallback COUNT still reports the real total.
    async with factory() as session:
        real_total = len((await session.exec(select(User.id))).all())
    assert total == real_total
