"""PostgreSQL integration coverage for the deterministic QA seed.

Opt-in: skipped unless ``HD_TEST_POSTGRES_URL`` points at a disposable
PostgreSQL database (the same guard as ``test_postgres_integration``). It runs
the real seed module against that database, twice, and asserts the fixtures are
deterministic, idempotent and valid against the native PostgreSQL enum types and
the single-OWNER partial unique index.
"""

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.commands.seed_qa_data import (
    SeedRefused,
    assert_safe_target,
    personas,
    seed,
    tickets as seed_tickets,
)
from app.core.database import _normalize_database_url
from app.enums.enums import Role, TicketPriority, TicketStatus
from app.models import Attachment, Comment, Notification, Ticket, TicketHistory, User

_PG_URL = os.environ.get("HD_TEST_POSTGRES_URL")
_SAFE = bool(_PG_URL) and any(
    marker in _PG_URL.lower() for marker in ("test", "verify", "ci")
)

pytestmark = pytest.mark.skipif(
    not _SAFE,
    reason="set HD_TEST_POSTGRES_URL to a disposable PostgreSQL database to run",
)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(_normalize_database_url(_PG_URL))
    yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(factory, tmp_path):
    """Seed the disposable database (idempotent) and return the counts."""
    first = await seed(tmp_path, session_factory=factory)
    second = await seed(tmp_path, session_factory=factory)
    return first, second, tmp_path


async def _count(factory, model) -> int:
    async with factory() as session:
        return (await session.exec(select(func.count()).select_from(model))).one()


async def test_seed_is_idempotent(seeded, factory):
    first, second, _ = seeded
    for key in ("users", "tickets", "comments", "history", "notifications", "attachments"):
        assert first[key] == second[key], f"{key} changed between runs"
    # Nothing new was created on the second run.
    assert second["_created_comments"] == 0
    assert second["_created_history"] == 0
    assert second["_created_notifications"] == 0
    assert second["_created_attachments"] == 0
    assert await _count(factory, User) >= len(personas())
    assert await _count(factory, Ticket) >= len(seed_tickets())


async def test_seed_covers_every_status_and_priority(seeded, factory):
    async with factory() as session:
        statuses = {
            row for row in (await session.exec(select(Ticket.status).distinct())).all()
        }
        priorities = {
            row for row in (await session.exec(select(Ticket.priority).distinct())).all()
        }
    assert statuses == set(TicketStatus)
    assert priorities == set(TicketPriority)


async def test_seed_has_exactly_one_owner(seeded, factory):
    async with factory() as session:
        owners = (
            await session.exec(select(User).where(User.role == Role.OWNER))
        ).all()
    assert len(owners) == 1
    assert owners[0].is_active is True


async def test_seed_roles_and_inactive_persona(seeded, factory):
    async with factory() as session:
        rows = (await session.exec(select(User))).all()
    by_email = {u.email: u for u in rows if u.email.endswith("@example.test")}
    assert by_email["qa.admin@example.test"].role == Role.ADMIN
    assert by_email["qa.agent.aria@example.test"].role == Role.AGENT
    assert by_email["qa.customer.alex@example.test"].role == Role.CUSTOMER
    assert by_email["qa.inactive@example.test"].is_active is False


async def test_seed_has_public_and_internal_comments(seeded, factory):
    async with factory() as session:
        public = (
            await session.exec(select(Comment).where(Comment.is_internal.is_(False)))
        ).all()
        internal = (
            await session.exec(select(Comment).where(Comment.is_internal.is_(True)))
        ).all()
    assert public and internal


async def test_seed_has_read_and_unread_notifications(seeded, factory):
    async with factory() as session:
        read = (
            await session.exec(select(Notification).where(Notification.is_read.is_(True)))
        ).all()
        unread = (
            await session.exec(select(Notification).where(Notification.is_read.is_(False)))
        ).all()
    assert read and unread


async def test_seed_attachment_metadata_is_valid(seeded, factory, tmp_path):
    async with factory() as session:
        attachments = (await session.exec(select(Attachment))).all()
    assert attachments
    for attachment in attachments:
        assert attachment.size_bytes >= 0
        assert (tmp_path / attachment.storage_key).is_file()


async def test_seed_history_covers_key_events(seeded, factory):
    async with factory() as session:
        events = {row for row in (await session.exec(select(TicketHistory.event_type).distinct())).all()}
    assert {"TICKET_CREATED", "TICKET_ASSIGNED", "STATUS_CHANGED", "PRIORITY_CHANGED"} <= events


def test_seed_guard_refuses_remote_and_unknown_targets():
    with pytest.raises(SeedRefused):
        assert_safe_target("postgresql+psycopg://u:p@db.example.com/appdb")
    with pytest.raises(SeedRefused):
        assert_safe_target("postgresql+psycopg://u:p@127.0.0.1:5432/production")
    # A loopback QA database is accepted.
    assert_safe_target(
        "postgresql+psycopg://qa_test:qa_test_only@127.0.0.1:55439/helpdesk_qa"
    )


async def test_seed_users_have_unique_deterministic_ids(seeded, factory):
    async with factory() as session:
        rows = (
            await session.exec(select(User).where(User.email.like("%@example.test")))
        ).all()
    ids = [u.id for u in rows]
    assert len(ids) == len(set(ids))
    assert all(isinstance(i, uuid.UUID) for i in ids)
    # A second run must not have duplicated any persona.
    emails = [u.email for u in rows]
    assert len(emails) == len(set(emails))
