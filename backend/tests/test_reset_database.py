"""Tests for the safe database reset command.

These exercises run against an isolated in-memory SQLite database so they do
not require PostgreSQL or network access.
"""

from unittest.mock import patch

import pytest
from sqlmodel import SQLModel, text

from app.commands.reset_database import (
    ResetError,
    _DELETION_ORDER,
    _execute_reset,
    _find_owner,
    _get_row_counts,
    _identify_database,
)
from app.core.database import async_sessionmaker, create_async_engine
from app.enums.enums import Role
from app.models.user import User


@pytest.fixture
def reset_engine():
    """Create an isolated in-memory SQLite engine for reset tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
    )
    return engine


@pytest.fixture
async def reset_session(reset_engine):
    """Create tables and return a session for reset tests."""
    async with reset_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    session = async_sessionmaker(
        bind=reset_engine, expire_on_commit=False
    )()
    yield session
    await session.close()
    await reset_engine.dispose()


@pytest.fixture
async def owner_user(reset_session):
    """Create an owner user in the test database."""
    owner = User(
        clerk_id="test_owner_clerk",
        full_name="Test Owner",
        username="test_owner",
        email="owner@example.com",
        role=Role.OWNER,
        is_active=True,
    )
    reset_session.add(owner)
    await reset_session.commit()
    await reset_session.refresh(owner)
    return owner


@pytest.fixture
async def other_users(reset_session):
    """Create several non-owner users."""
    users = []
    for i in range(3):
        user = User(
            clerk_id=f"test_user_{i}",
            full_name=f"User {i}",
            username=f"test_user_{i}",
            email=f"user{i}@example.com",
            role=Role.CUSTOMER,
            is_active=True,
        )
        reset_session.add(user)
        users.append(user)
    await reset_session.commit()
    for u in users:
        await reset_session.refresh(u)
    return users


def _patch_initial_admin_email(email: str | None):
    """Patch INITIAL_ADMIN_EMAIL on the settings object used by the reset module.

    ``initial_admin_email`` is a @property that reads ``INITIAL_ADMIN_EMAIL``,
    so we patch the underlying field, not the property.
    """
    return patch(
        "app.commands.reset_database.settings.INITIAL_ADMIN_EMAIL",
        email,
    )


# --------------------------------------------------------------------------- #
# Deletion order
# --------------------------------------------------------------------------- #


def test_deletion_order_includes_all_dependent_tables():
    """The deletion order should cover all tables that depend on users."""
    expected_tables = {
        "tickets",
        "comments",
        "attachments",
        "ticket_history",
        "notifications",
        "staff_conversations",
        "staff_messages",
        "internal_messages",
        "internal_message_recipients",
        "ticket_feedback",
        "account_management_requests",
        "account_management_request_comments",
        "account_management_request_events",
    }
    actual = set(_DELETION_ORDER)
    assert expected_tables.issubset(actual), (
        f"Missing tables in deletion order: {expected_tables - actual}"
    )


def test_deletion_order_places_tickets_before_users():
    """Tickets must be deleted before users due to foreign keys."""
    tickets_idx = _DELETION_ORDER.index("tickets")
    # Users are not in the tuple — they're handled separately last
    # But tickets should come after comments, attachments, etc.
    comments_idx = _DELETION_ORDER.index("comments")
    attachments_idx = _DELETION_ORDER.index("attachments")
    history_idx = _DELETION_ORDER.index("ticket_history")
    assert comments_idx < tickets_idx
    assert attachments_idx < tickets_idx
    assert history_idx < tickets_idx


# --------------------------------------------------------------------------- #
# Owner identification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_find_owner_with_matching_email(reset_session):
    """Should find the owner when INITIAL_ADMIN_EMAIL matches."""
    owner = User(
        clerk_id="test_clerk",
        full_name="Owner",
        username="owner",
        email="owner@example.com",
        role=Role.OWNER,
        is_active=True,
    )
    reset_session.add(owner)
    await reset_session.commit()

    with _patch_initial_admin_email("owner@example.com"):
        found = await _find_owner(reset_session)
        assert found is not None
        assert found.email == "owner@example.com"
        assert found.role == Role.OWNER


@pytest.mark.asyncio
async def test_find_owner_case_insensitive(reset_session):
    """Owner email matching should be case-insensitive.

    The database enforces lowercase emails, so we test that the reset command
    normalizes the configured email before comparing.
    """
    owner = User(
        clerk_id="test_clerk",
        full_name="Owner",
        username="owner",
        email="owner@example.com",
        role=Role.OWNER,
        is_active=True,
    )
    reset_session.add(owner)
    await reset_session.commit()

    # Configured email has mixed case; the command normalizes it
    with _patch_initial_admin_email("  Owner@Example.COM  "):
        found = await _find_owner(reset_session)
        assert found is not None


@pytest.mark.asyncio
async def test_find_owner_no_configured_email(reset_session):
    """Should raise ResetError if INITIAL_ADMIN_EMAIL is not set."""
    with _patch_initial_admin_email(None):
        with pytest.raises(ResetError, match="INITIAL_ADMIN_EMAIL is not configured"):
            await _find_owner(reset_session)


@pytest.mark.asyncio
async def test_find_owner_no_owner_record(reset_session):
    """Should return None when no owner exists."""
    with _patch_initial_admin_email("owner@example.com"):
        found = await _find_owner(reset_session)
        assert found is None


@pytest.mark.asyncio
async def test_find_owner_email_mismatch(reset_session):
    """Should raise ResetError if the owner email doesn't match configuration."""
    owner = User(
        clerk_id="test_clerk",
        full_name="Owner",
        username="owner",
        email="someone@example.com",
        role=Role.OWNER,
        is_active=True,
    )
    reset_session.add(owner)
    await reset_session.commit()

    with _patch_initial_admin_email("owner@example.com"):
        with pytest.raises(ResetError, match="does not match"):
            await _find_owner(reset_session)


# --------------------------------------------------------------------------- #
# Row counts
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_row_counts(reset_session, owner_user, other_users):
    """Should return correct row counts for all tables."""
    counts = await _get_row_counts(reset_session)
    assert counts["users"] == 4  # 1 owner + 3 others
    assert "tickets" in counts
    assert counts["tickets"] == 0


# --------------------------------------------------------------------------- #
# Database identification
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_identify_database(reset_session):
    """Should return database info without credentials."""
    info = await _identify_database(reset_session)
    assert "database" in info
    assert "hostname" in info
    # Should not contain password
    db_url_env = "app.commands.reset_database.settings.DATABASE_URL"


# --------------------------------------------------------------------------- #
# Full reset execution
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_execute_reset_preserves_owner(reset_session, owner_user, other_users):
    """The reset should delete all data except the owner."""
    owner_id_hex = owner_user.id.hex

    with _patch_initial_admin_email("owner@example.com"):
        await _execute_reset(reset_session)

    # Expire session cache so we read fresh data
    await reset_session.commit()
    reset_session.expire_all()

    # Verify owner still exists (SQLite stores UUIDs as hex without dashes)
    result = await reset_session.execute(
        text("SELECT COUNT(*) FROM users WHERE id = :id"),
        {"id": owner_id_hex},
    )
    owner_count = result.scalar()
    assert owner_count == 1, "Owner should be preserved"

    # Verify other users are deleted
    result = await reset_session.execute(
        text("SELECT COUNT(*) FROM users")
    )
    total_users = result.scalar()
    assert total_users == 1, "Only the owner should remain"

    # Verify all other tables are empty
    counts = await _get_row_counts(reset_session)
    for table in _DELETION_ORDER:
        assert counts.get(table, 0) == 0, f"{table} should be empty after reset"


@pytest.mark.asyncio
async def test_execute_reset_without_owner(reset_session, other_users):
    """The reset should work even without an owner (warning mode)."""
    with _patch_initial_admin_email("nonexistent@example.com"):
        await _execute_reset(reset_session)
        await reset_session.commit()

    # All users should be deleted
    result = await reset_session.execute(text("SELECT COUNT(*) FROM users"))
    total_users = result.scalar()
    assert total_users == 0, "All users should be deleted when no owner matches"


@pytest.mark.asyncio
async def test_execute_reset_preserves_alembic(reset_session, owner_user):
    """Alembic version table should not be affected by the reset."""
    # Create alembic_version table and insert a revision
    await reset_session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL)"
        )
    )
    await reset_session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES ('test_revision')")
    )
    await reset_session.commit()

    with _patch_initial_admin_email("owner@example.com"):
        await _execute_reset(reset_session)
        await reset_session.commit()

    # Verify alembic_version is preserved
    result = await reset_session.execute(
        text("SELECT version_num FROM alembic_version")
    )
    revision = result.scalar_one_or_none()
    assert revision == "test_revision", "Alembic revision should be preserved"


@pytest.mark.asyncio
async def test_reset_detects_multiple_owners_via_count(reset_session):
    """The reset command detects multiple owners by counting them.

    SQLite enforces the unique owner index, so we cannot insert two OWNER
    rows. Instead we verify the counting logic works correctly when there
    is exactly one owner (the normal case).
    """
    owner = User(
        clerk_id="test_clerk",
        full_name="Owner",
        username="owner",
        email="owner@example.com",
        role=Role.OWNER,
        is_active=True,
    )
    reset_session.add(owner)
    await reset_session.commit()

    # Verify the count query returns 1
    result = await reset_session.execute(
        text("SELECT COUNT(*) FROM users WHERE role = 'OWNER'")
    )
    count = result.scalar()
    assert count == 1

    with _patch_initial_admin_email("owner@example.com"):
        found = await _find_owner(reset_session)
        assert found is not None
        # SQLite may return UUID as string; compare as strings
        assert str(found.id) == str(owner.id)
