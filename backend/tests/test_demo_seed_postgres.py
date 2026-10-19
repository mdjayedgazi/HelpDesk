"""PostgreSQL integration coverage for the realistic demo seed.

Opt-in: skipped unless ``HD_DEMO_SEED_POSTGRES_URL`` points at a disposable
PostgreSQL database whose name contains ``verify``/``demo``/``test``/``ci``.

Unlike the other PostgreSQL test modules this one asserts *exact* totals, so it
must run against a **dedicated, otherwise-empty** database. Point it at a
throwaway database (never the live Neon target and never the shared test DB)::

    docker exec helpdesk-migtest psql -U helpdesk -d postgres \\
        -c "CREATE DATABASE helpdesk_demo_verify"
    cd backend
    HD_DEMO_SEED_POSTGRES_URL="postgresql+psycopg://helpdesk:disposable@127.0.0.1:55432/helpdesk_demo_verify" \\
        uv run pytest tests/test_demo_seed_postgres.py -q

It runs the real seed module twice, so it also proves idempotency.
"""

import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.commands import seed_demo_data as sd
from app.core.database import _normalize_database_url
from app.enums.enums import (
    EscalationStatus,
    Role,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models import (
    AccountManagementRequest,
    AccountRequestEvent,
    Attachment,
    Comment,
    Notification,
    StaffConversation,
    StaffMessage,
    Ticket,
    TicketHistory,
    User,
)

_PG_URL = os.environ.get("HD_DEMO_SEED_POSTGRES_URL")
_SAFE = bool(_PG_URL) and any(
    marker in _PG_URL.lower() for marker in ("verify", "demo", "test", "ci")
)

pytestmark = pytest.mark.skipif(
    not _SAFE,
    reason="set HD_DEMO_SEED_POSTGRES_URL to a dedicated disposable database",
)


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(_normalize_database_url(_PG_URL))
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    # Ensure exactly one OWNER exists (the seed refuses to run without one).
    async with async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )() as session:
        owner = (await session.exec(select(User).where(User.role == Role.OWNER))).first()
        if owner is None:
            session.add(
                User(
                    id=sd._uid("user", "__owner__"),
                    clerk_id="user_DEMO_OWNER_FIXTURE",
                    full_name="Demo Fixture Owner",
                    username="demo_owner_fixture",
                    email="demo.owner@example.test",
                    password_hash=None,
                    role=Role.OWNER,
                    is_active=True,
                )
            )
            await session.commit()
    yield async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(factory, tmp_path):
    first = await sd.seed(tmp_path, session_factory=factory)
    second = await sd.seed(tmp_path, session_factory=factory)
    return first, second, tmp_path


async def _count(factory, model) -> int:
    async with factory() as session:
        return int((await session.exec(select(func.count()).select_from(model))).one())


# --------------------------------------------------------------------------- #
# Guards (no database needed)
# --------------------------------------------------------------------------- #


def test_guard_refuses_wrong_confirm_token():
    with pytest.raises(sd.SeedRefused):
        sd.assert_confirm(None)
    with pytest.raises(sd.SeedRefused):
        sd.assert_confirm("HD-DEMO-20261019 @ evil.example.com/neondb")
    sd.assert_confirm(sd.EXPECTED_TOKEN)


def test_guard_refuses_non_neon_and_wrong_db():
    with pytest.raises(sd.SeedRefused):
        sd.assert_neon_target(None)
    with pytest.raises(sd.SeedRefused):
        sd.assert_neon_target("postgresql+psycopg://u:p@127.0.0.1:5432/neondb")
    with pytest.raises(sd.SeedRefused):
        sd.assert_neon_target(f"postgresql+psycopg://u:p@{sd.EXPECTED_HOST}/otherdb")
    # The verified target is accepted.
    sd.assert_neon_target(f"postgresql+psycopg://u:p@{sd.EXPECTED_HOST}/neondb")


def test_guard_refuses_uploads_outside_tmp():
    # The repository directory is not under /tmp.
    repo_dir = str(Path(__file__).resolve().parent)
    with pytest.raises(sd.SeedRefused):
        sd.assert_safe_upload_dir(repo_dir)
    assert sd.assert_safe_upload_dir("/tmp/helpdesk-demo-uploads")


def test_guard_refuses_production_environment():
    with pytest.raises(sd.SeedRefused):
        sd.assert_not_production({"HELPDESK_ENVIRONMENT": "production"})
    sd.assert_not_production({"HELPDESK_ENVIRONMENT": "development"})


# --------------------------------------------------------------------------- #
# Deterministic data-level invariants (no database needed)
# --------------------------------------------------------------------------- #


def test_specs_meet_the_required_targets():
    users = sd.demo_users()
    tickets = sd.ticket_specs(users)
    assert len(users) == 99
    assert len(tickets) == sd.N_TICKETS >= 100
    assert len(sd.comment_specs(users, tickets)) >= 200
    assert len(sd.history_specs(users, tickets)) >= 300
    assert len(sd.notification_specs(users, tickets)) >= 100
    assert len(sd.attachment_specs(tickets)) >= 10
    assert len(sd.staff_conversation_specs(users)) >= 10
    assert (
        len(sd.staff_message_specs(sd.staff_conversation_specs(users))) >= 30
    )
    assert len(sd.account_request_specs(users)) >= 10


def test_spec_emails_and_usernames_are_unique_and_reserved():
    users = sd.demo_users()
    usernames = [u.username for u in users]
    emails = [u.email for u in users]
    assert len(set(usernames)) == len(usernames)
    assert len(set(emails)) == len(emails)
    assert all(e.endswith("@example.test") for e in emails)


def test_spec_only_staff_author_internal_comments():
    users = sd.demo_users()
    staff = {u.key for u in users if u.role in (Role.AGENT, Role.ADMIN)}
    internal = [c for c in sd.comment_specs(users, sd.ticket_specs(users)) if c["internal"]]
    assert internal
    assert all(c["author_key"] in staff for c in internal)


# --------------------------------------------------------------------------- #
# Database-backed coverage
# --------------------------------------------------------------------------- #


async def test_seed_is_idempotent(seeded, factory):
    first, second, _ = seeded
    for key, counts in first.counts.items():
        assert counts["inserted"] > 0, f"{key} inserted nothing"
        assert second.counts[key]["inserted"] == 0, f"{key} duplicated on rerun"
        assert second.counts[key]["reused"] == counts["inserted"]
    assert second.owner_after == first.owner_before


async def test_seed_exact_user_composition(seeded, factory):
    assert await _count(factory, User) == 100
    async with factory() as session:
        by_role = {
            role: count
            for role, count in (
                await session.exec(
                    select(User.role, func.count(User.id)).group_by(User.role)
                )
            ).all()
        }
    assert by_role[Role.OWNER] == 1
    assert by_role[Role.ADMIN] == 5
    assert by_role[Role.AGENT] == 15
    assert by_role[Role.CUSTOMER] == 79


async def test_seed_preserves_single_owner(seeded, factory):
    async with factory() as session:
        owners = (
            await session.exec(select(User).where(User.role == Role.OWNER))
        ).all()
    assert len(owners) == 1
    assert owners[0].is_active is True


async def test_seed_tickets_cover_all_states(seeded, factory):
    async with factory() as session:
        statuses = set((await session.exec(select(Ticket.status).distinct())).all())
        priorities = set(
            (await session.exec(select(Ticket.priority).distinct())).all()
        )
        categories = set(
            (await session.exec(select(Ticket.category).distinct())).all()
        )
    assert statuses == set(TicketStatus)
    assert priorities == set(TicketPriority)
    assert categories == set(TicketCategory)
    assert await _count(factory, Ticket) >= 100


async def test_seed_has_assigned_and_unassigned_tickets(seeded, factory):
    async with factory() as session:
        assigned = int(
            (
                await session.exec(
                    select(func.count(Ticket.id)).where(
                        Ticket.assignee_user_id.is_not(None)
                    )
                )
            ).one()
        )
        unassigned = int(
            (
                await session.exec(
                    select(func.count(Ticket.id)).where(
                        Ticket.assignee_user_id.is_(None)
                    )
                )
            ).one()
        )
    assert assigned > 0 and unassigned > 0
    # Every assigned ticket must reference an AGENT (never a customer/admin).
    async with factory() as session:
        assignee_roles = set(
            (
                await session.exec(
                    select(User.role)
                    .join(Ticket, Ticket.assignee_user_id == User.id)
                    .distinct()
                )
            ).all()
        )
    assert assignee_roles <= {Role.AGENT}


async def test_seed_comments_include_public_and_internal(seeded, factory):
    async with factory() as session:
        internal_authors = (
            await session.exec(
                select(User.role)
                .join(Comment, Comment.author_user_id == User.id)
                .where(Comment.is_internal.is_(True))
                .distinct()
            )
        ).all()
        public = int(
            (
                await session.exec(
                    select(func.count(Comment.id)).where(
                        Comment.is_internal.is_(False)
                    )
                )
            ).one()
        )
        internal = int(
            (
                await session.exec(
                    select(func.count(Comment.id)).where(Comment.is_internal.is_(True))
                )
            ).one()
        )
    assert public >= 200
    assert internal > 0
    # Customers can never author an internal-only note.
    assert Role.CUSTOMER not in set(internal_authors)


async def test_seed_history_covers_key_events(seeded, factory):
    async with factory() as session:
        events = set(
            (await session.exec(select(TicketHistory.event_type).distinct())).all()
        )
    assert {
        "TICKET_CREATED",
        "TICKET_ASSIGNED",
        "STATUS_CHANGED",
        "PRIORITY_CHANGED",
    } <= events
    assert await _count(factory, TicketHistory) >= 300


async def test_seed_notifications_read_and_unread(seeded, factory):
    async with factory() as session:
        read = (
            await session.exec(select(Notification).where(Notification.is_read.is_(True)))
        ).all()
        unread = (
            await session.exec(
                select(Notification).where(Notification.is_read.is_(False))
            )
        ).all()
    assert read and unread
    assert len(read) + len(unread) >= 100


async def test_seed_attachments_have_files(seeded, factory, tmp_path):
    async with factory() as session:
        attachments = (await session.exec(select(Attachment))).all()
    assert len(attachments) >= 10
    for attachment in attachments:
        assert attachment.size_bytes >= 0
        assert (tmp_path / attachment.storage_key).is_file()


async def test_seed_staff_conversations_and_messages(seeded, factory):
    async with factory() as session:
        conversations = (await session.exec(select(StaffConversation))).all()
        messages = (await session.exec(select(StaffMessage))).all()
        owner = (await session.exec(select(User).where(User.role == Role.OWNER))).first()
        staff_ids = {c.staff_user_id for c in conversations}
        message_senders = {m.sender_user_id for m in messages}
    assert len(conversations) >= 10
    assert len(messages) >= 30
    assert all(c.owner_user_id == owner.id for c in conversations)
    # One thread per staff member (enforced by a unique index) and only the
    # Owner / the conversation's staff participant ever send messages.
    assert len(staff_ids) == len(conversations)
    assert message_senders <= (staff_ids | {owner.id})


async def test_seed_account_requests_cover_states(seeded, factory):
    async with factory() as session:
        requests = (await session.exec(select(AccountManagementRequest))).all()
        events = (await session.exec(select(AccountRequestEvent))).all()
        target_ids = {
            row for row in (await session.exec(select(User.id))).all()
        }
    assert len(requests) >= 10
    states = {r.status for r in requests}
    assert len(states) >= 3
    assert EscalationStatus.PENDING in states
    # Every request targets a real user and carries a snapshot.
    for request in requests:
        assert request.target_user_id in target_ids
        assert request.target_email_snapshot
    # Decided requests carry a decision; pending ones do not.
    for request in requests:
        if request.status == EscalationStatus.PENDING:
            assert request.decided_at is None
        elif request.status in {
            EscalationStatus.APPROVED,
            EscalationStatus.REJECTED,
            EscalationStatus.COMPLETED,
        }:
            assert request.decided_at is not None
    assert events


async def test_seed_users_have_deterministic_unique_ids(seeded, factory):
    async with factory() as session:
        rows = (
            await session.exec(
                select(User).where(User.email.like("%@example.test"))
            )
        ).all()
    ids = [u.id for u in rows]
    assert len(ids) == len(set(ids))
    assert all(isinstance(i, uuid.UUID) for i in ids)
    # uuid5 of the fixed namespace -> stable across runs.
    assert sd._uid("user", "customer_00") in set(ids)
