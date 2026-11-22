"""Regression tests for the 0012_staff_mentions migration on real PostgreSQL.

SQLite cannot reproduce the production failure: it was a PostgreSQL
``UniqueViolation`` raised by the legacy single-column unique index
``uq_staff_conversations_staff_user`` *during* the canonicalisation UPDATE of
the 0012 migration.

These tests build the exact legacy schema at ``0011``, seed conversations the
way the real database had them, and then drive Alembic against a throw-away
database. They are skipped unless ``HD_TEST_POSTGRES_URL`` points at a
disposable database whose name contains ``test``/``verify``/``ci`` (see
``tests/_disposable_db_guard``). They never touch a real database, never print
credentials, and never truncate the shared disposable database: each test
creates and drops its **own** database.
"""

import os
import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests._disposable_db_guard import is_disposable

_PG_URL = os.environ.get("HD_TEST_POSTGRES_URL")
_SAFE = is_disposable(_PG_URL)

pytestmark = pytest.mark.skipif(
    not _SAFE,
    reason="set HD_TEST_POSTGRES_URL to a disposable PostgreSQL database to run",
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OWNER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
AGENT_A = uuid.UUID("ff000000-0000-0000-0000-000000000001")
AGENT_B = uuid.UUID("ff000000-0000-0000-0000-000000000002")
# Sorts *before* the Owner, so canonicalisation must swap it.
EARLY_AGENT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _sync_url() -> str:
    assert _PG_URL is not None
    return _PG_URL


def _admin_engine():
    """A connection to the disposable server's maintenance database."""
    return create_engine(_sync_url(), isolation_level="AUTOCOMMIT")


@pytest.fixture()
def database(monkeypatch) -> Iterator[str]:
    """Create an isolated database, point Alembic/settings at it, then drop it."""
    name = f"mig012_{uuid.uuid4().hex[:12]}"
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))

    base = _sync_url().rsplit("/", 1)[0]  # strip the database name
    scoped = f"{base}/{name}"

    # env.py reads these at run time from the shared settings object.
    from app.core.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", scoped)
    monkeypatch.setattr(settings, "MIGRATION_DATABASE_URL", scoped)
    monkeypatch.setattr(settings, "AUTO_CREATE_TABLES", False)

    try:
        yield scoped
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


def _alembic_config() -> Config:
    cfg = Config(os.path.join(BACKEND_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_ROOT, "migrations"))
    return cfg


def _engine(url: str):
    return create_engine(url)


def _seed_legacy(url: str, *, owner_conversations: int = 2) -> None:
    """Seed the pre-0012 schema with conversations that force canonical swaps.

    Every legacy row is ``(staff, owner)``. The Owner id is chosen so that
    canonicalisation puts the Owner at ``participant_a_id`` for several rows —
    exactly the condition the stale single-column index rejected in production.
    """
    engine = _engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, full_name, username, email, role, "
                "is_active, created_at, updated_at) VALUES "
                "(:o,'c_o','Owner','owner','o@e.com','OWNER',true,now(),now()),"
                "(:a,'c_a','Agent A','agenta','a@e.com','AGENT',true,now(),now()),"
                "(:b,'c_b','Admin B','adminb','b@e.com','ADMIN',true,now(),now()),"
                "(:z,'c_z','Zed','zed','z@e.com','AGENT',true,now(),now())"
            ),
            {"o": OWNER_ID, "a": AGENT_A, "b": AGENT_B, "z": EARLY_AGENT},
        )
        pairs = [(AGENT_A, "agent a"), (AGENT_B, "admin b"), (EARLY_AGENT, "zed")]
        for staff, subject in pairs[:owner_conversations]:
            cid = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO staff_conversations "
                    "(id, staff_user_id, owner_user_id, subject, created_at, "
                    "updated_at, last_message_at) "
                    "VALUES (:id,:s,:o,:sub,now(),now(),now())"
                ),
                {"id": cid, "s": staff, "o": OWNER_ID, "sub": subject},
            )
            conn.execute(
                text(
                    "INSERT INTO staff_messages "
                    "(id, conversation_id, sender_user_id, body, created_at) "
                    "VALUES (:id,:c,:s,'hi',now())"
                ),
                {"id": uuid.uuid4(), "c": cid, "s": staff},
            )
    engine.dispose()


def test_upgrade_migrates_legacy_conversations_without_unique_violation(database):
    """The production failure: canonicalising participants tripped the old index.

    Seeded with three Owner conversations; canonical order puts the Owner at
    ``participant_a_id`` for two of them (owner UUID is the smaller one for the
    staff UUIDs that sort after it) and for the early-agent row the early agent
    is smaller — every row is migrated, none dropped or duplicated.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0011_query_indexes")
    _seed_legacy(database, owner_conversations=3)

    # This is the exact regression: must not raise UniqueViolation.
    command.upgrade(cfg, "head")

    engine = _engine(database)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        total = conn.execute(text("SELECT count(*) FROM staff_conversations")).scalar()
        messages = conn.execute(text("SELECT count(*) FROM staff_messages")).scalar()
        canonical = conn.execute(
            text(
                "SELECT bool_and(participant_a_id < participant_b_id) "
                "FROM staff_conversations"
            )
        ).scalar()
        distinct_pairs = conn.execute(
            text(
                "SELECT count(DISTINCT (participant_a_id, participant_b_id)) "
                "FROM staff_conversations"
            )
        ).scalar()
        legacy_index = conn.execute(
            text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname = 'uq_staff_conversations_staff_user'"
            )
        ).scalar()
    engine.dispose()

    assert version == "0012_staff_mentions"
    assert total == 3 and messages == 3, "conversations/messages must be preserved"
    assert canonical is True
    assert distinct_pairs == 3
    assert legacy_index == 0

    # Re-running upgrade is a no-op.
    command.upgrade(cfg, "head")


def test_new_constraints_reject_duplicates_and_self_conversations(database):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    engine = _engine(database)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, full_name, username, email, role, "
                "is_active, created_at, updated_at) VALUES "
                "(:a,'c_a','A','a','a@e.com','AGENT',true,now(),now()),"
                "(:b,'c_b','B','b','b@e.com','AGENT',true,now(),now())"
            ),
            {"a": AGENT_A, "b": AGENT_B},
        )
        conn.execute(
            text(
                "INSERT INTO staff_conversations "
                "(id, participant_a_id, participant_b_id, subject) "
                "VALUES (:id,:a,:b,'pair')"
            ),
            {"id": uuid.uuid4(), "a": AGENT_A, "b": AGENT_B},
        )

    with pytest.raises(Exception) as dup, engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO staff_conversations "
                "(id, participant_a_id, participant_b_id, subject) "
                "VALUES (:id,:a,:b,'dup')"
            ),
            {"id": uuid.uuid4(), "a": AGENT_A, "b": AGENT_B},
        )
    assert "uq_staff_conversations_participant_pair" in str(dup.value)

    with pytest.raises(Exception) as self_conv, engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO staff_conversations "
                "(id, participant_a_id, participant_b_id, subject) "
                "VALUES (:id,:a,:a,'self')"
            ),
            {"id": uuid.uuid4(), "a": AGENT_A},
        )
    assert "ck_staff_conversations_distinct_participants" in str(self_conv.value)
    engine.dispose()


def test_downgrade_refuses_lossy_conversations(database):
    """The legacy schema cannot represent a staff-to-staff conversation."""
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    engine = _engine(database)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, full_name, username, email, role, "
                "is_active, created_at, updated_at) VALUES "
                "(:o,'c_o','Owner','owner','o@e.com','OWNER',true,now(),now()),"
                "(:a,'c_a','A','a','a@e.com','AGENT',true,now(),now()),"
                "(:b,'c_b','B','b','b@e.com','AGENT',true,now(),now())"
            ),
            {"o": OWNER_ID, "a": AGENT_A, "b": AGENT_B},
        )
        conn.execute(
            text(
                "INSERT INTO staff_conversations "
                "(id, participant_a_id, participant_b_id, subject) "
                "VALUES (:id,:a,:b,'staff to staff')"
            ),
            {"id": uuid.uuid4(), "a": AGENT_A, "b": AGENT_B},
        )

    with pytest.raises(Exception) as refused:
        command.downgrade(cfg, "0011_query_indexes")
    assert "Cannot downgrade" in str(refused.value)

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        total = conn.execute(text("SELECT count(*) FROM staff_conversations")).scalar()
    engine.dispose()
    assert version == "0012_staff_mentions"
    assert total == 1


def test_downgrade_roundtrip_for_owner_conversations(database):
    """When every conversation includes the Owner, downgrade is lossless."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0011_query_indexes")

    engine = _engine(database)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, clerk_id, full_name, username, email, role, "
                "is_active, created_at, updated_at) VALUES "
                "(:o,'c_o','Owner','owner','o@e.com','OWNER',true,now(),now()),"
                "(:a,'c_a','A','a','a@e.com','AGENT',true,now(),now()),"
                "(:z,'c_z','Z','z','z@e.com','AGENT',true,now(),now())"
            ),
            {"o": OWNER_ID, "a": AGENT_A, "z": EARLY_AGENT},
        )
        for staff, subject in ((AGENT_A, "a"), (EARLY_AGENT, "z")):
            conn.execute(
                text(
                    "INSERT INTO staff_conversations "
                    "(id, staff_user_id, owner_user_id, subject, created_at, updated_at) "
                    "VALUES (:id,:s,:o,:sub,now(),now())"
                ),
                {"id": uuid.uuid4(), "s": staff, "o": OWNER_ID, "sub": subject},
            )
    engine.dispose()

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0011_query_indexes")

    engine = _engine(database)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        total = conn.execute(text("SELECT count(*) FROM staff_conversations")).scalar()
        owner_rows = conn.execute(
            text(
                "SELECT count(*) FROM staff_conversations sc "
                "JOIN users u ON u.id = sc.owner_user_id WHERE u.role::text = 'OWNER'"
            )
        ).scalar()
        distinct_staff = conn.execute(
            text("SELECT count(DISTINCT staff_user_id) FROM staff_conversations")
        ).scalar()
        legacy_index = conn.execute(
            text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE indexname = 'uq_staff_conversations_staff_user'"
            )
        ).scalar()
    engine.dispose()

    assert version == "0011_query_indexes"
    assert total == 2 and owner_rows == 2 and distinct_staff == 2
    assert legacy_index == 1


def test_mention_schema_and_enum_present(database):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    engine = _engine(database)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name IN "
                    "('staff_message_mentions','internal_message_mentions')"
                )
            )
        }
        enum_label = conn.execute(
            text(
                "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'notificationtype' AND e.enumlabel = 'STAFF_MENTION'"
            )
        ).scalar()
    engine.dispose()
    assert tables == {"staff_message_mentions", "internal_message_mentions"}
    assert enum_label == 1


def test_upgrade_is_idempotent_when_enum_label_already_committed(database):
    """A failed first attempt may have committed the enum label but not the rest.

    The original 0012 added ``STAFF_MENTION`` in an ``autocommit_block`` before
    the canonicalisation failure, so the production database can be at ``0011``
    with the label already present. The corrected migration must still succeed.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0011_query_indexes")

    # Pre-commit the enum label exactly like the failed production run: the
    # label was added in an ``autocommit_block`` that does not roll back.
    admin = create_engine(database, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "ALTER TYPE public.notificationtype "
                "ADD VALUE IF NOT EXISTS 'STAFF_MENTION'"
            )
        )
    admin.dispose()

    _seed_legacy(database, owner_conversations=2)

    command.upgrade(cfg, "head")

    engine = _engine(database)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        total = conn.execute(text("SELECT count(*) FROM staff_conversations")).scalar()
        labels = conn.execute(
            text(
                "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = 'notificationtype' AND e.enumlabel = 'STAFF_MENTION'"
            )
        ).scalar()
    engine.dispose()
    assert version == "0012_staff_mentions"
    assert total == 2
    assert labels == 1


def test_empty_database_downgrades_cleanly(database):
    """The CI migration job downgrades a fresh install; nothing must be refused.

    A database with no conversations has nothing the legacy schema cannot hold,
    so the lossy-downgrade guard must allow it even without an OWNER account.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "0011_query_indexes")

    engine = _engine(database)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        columns = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'staff_conversations'"
                )
            )
        }
    engine.dispose()
    assert version == "0011_query_indexes"
    assert {"staff_user_id", "owner_user_id"} <= columns
