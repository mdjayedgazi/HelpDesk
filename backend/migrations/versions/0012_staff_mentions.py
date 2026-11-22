"""universal staff messaging + structured @mentions

Revision ID: 0012_staff_mentions
Revises: 0011_query_indexes
Create Date: 2026-11-22 00:00:00.000000

What this revision changes
--------------------------
* Generalizes ``staff_conversations`` from a hard-wired staff <-> Owner pair to
  any two eligible staff members. ``staff_user_id`` / ``owner_user_id`` are
  renamed to ``participant_a_id`` / ``participant_b_id`` and every existing row
  is normalized so ``participant_a_id < participant_b_id`` (canonical order).
  Existing conversations and messages are preserved unchanged; only the two
  participant column names and their ordering change.
* Replaces the old "one thread per staff member" unique index with a unique
  constraint on the canonical participant **pair**, so there is exactly one
  thread per pair regardless of who starts it.
* Adds ``staff_message_mentions`` and ``internal_message_mentions``: one row per
  (message, mentioned employee), referencing the real ``users.id``. One row per
  pair means a duplicate mention in one message is stored once.
* Appends the ``STAFF_MENTION`` label to the shared ``notificationtype`` enum.

Ordering defect fixed here (production hotfix)
----------------------------------------------
The original version of this migration renamed the participant columns and then
canonicalized participant order **before** dropping the legacy single-column
unique index ``uq_staff_conversations_staff_user``. That index was created by
``0004`` with ``op.create_index(..., unique=True)`` — a standalone UNIQUE INDEX,
not a table constraint — and it kept enforcing "one conversation per
``staff_user_id``". After canonicalization the same person (typically the Owner)
legitimately becomes ``participant_a_id`` of many rows, so the UPDATE tripped
that stale index with a ``UniqueViolation`` on ``participant_a_id``. On the real
database the migration aborted and rolled back (PostgreSQL DDL is
transactional); on an *empty* database it never surfaced because the UPDATE had
no rows to move.

The corrected order is:

1. drop the legacy ``uq_staff_conversations_staff_user`` unique index,
2. rename the columns,
3. canonicalize participants,
4. add the unique participant-pair constraint + the distinct-participants CHECK,
5. create the two mention tables,
6. append the enum label.

Enum idempotency
----------------
The original run added ``STAFF_MENTION`` in an ``autocommit_block`` *before* the
failure. Such blocks are not rolled back, so on the production database the enum
label may already exist while ``alembic_version`` is still ``0011``. The
``IF NOT EXISTS`` guard makes the corrected migration safe to run on that
partially-applied state as well as on a virgin database.

Downgrade safety
----------------
The old schema cannot represent conversations that do not include the Owner, and
its single-column unique index forbids one user appearing in two threads. The
universal model permits both. A blind downgrade would therefore either fail
mid-way or lose rows. ``downgrade`` refuses (with a clear error) when the data
cannot be represented faithfully, instead of silently destroying history.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_staff_mentions"
down_revision: str | None = "0011_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The legacy single-column unique index, created as a bare index by 0004.
_LEGACY_STAFF_UNIQUE_INDEX = "uq_staff_conversations_staff_user"
_LEGACY_OWNER_INDEX = "ix_staff_conversations_owner_user_id"


def _has_legacy_index(table: str, index_name: str) -> bool:
    """Whether ``index_name`` exists on ``table`` (online mode only).

    Offline mode (``alembic upgrade --sql``) has no catalog, so it assumes the
    index exists and emits the drop unconditionally — the documented SQL for a
    fresh database that ran 0004.
    """
    if op.get_context().as_sql:
        return True
    inspector = sa.inspect(op.get_bind())
    return any(
        index.get("name") == index_name for index in inspector.get_indexes(table)
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    if is_postgresql:
        # Add the new notification label first. ``autocommit_block`` is not part
        # of the migration transaction; ``IF NOT EXISTS`` keeps a re-run after a
        # partially-applied failure safe.
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE public.notificationtype "
                "ADD VALUE IF NOT EXISTS 'STAFF_MENTION'"
            )

    # --- 1. Remove the obsolete single-participant uniqueness FIRST ----------
    # It is a standalone unique INDEX (0004 used create_index(unique=True)), so
    # it must be dropped as an index. Dropping it *after* canonicalization — as
    # the original migration did — fails on any non-trivial dataset because the
    # canonical order puts one user (the Owner) at participant_a for many rows.
    if _has_legacy_index("staff_conversations", _LEGACY_STAFF_UNIQUE_INDEX):
        op.drop_index(_LEGACY_STAFF_UNIQUE_INDEX, table_name="staff_conversations")
    if _has_legacy_index("staff_conversations", _LEGACY_OWNER_INDEX):
        op.drop_index(_LEGACY_OWNER_INDEX, table_name="staff_conversations")

    # --- 2. Rename the participant columns ---------------------------------
    op.alter_column(
        "staff_conversations",
        "staff_user_id",
        new_column_name="participant_a_id",
    )
    op.alter_column(
        "staff_conversations",
        "owner_user_id",
        new_column_name="participant_b_id",
    )

    # --- 3. Canonicalize participants (smaller UUID first) ------------------
    # PostgreSQL compares UUIDs natively; on other dialects the text cast is an
    # equivalent total order.
    if is_postgresql:
        op.execute(
            "UPDATE staff_conversations "
            "SET participant_a_id = participant_b_id, "
            "    participant_b_id = participant_a_id "
            "WHERE participant_a_id > participant_b_id"
        )
    else:
        op.execute(
            "UPDATE staff_conversations "
            "SET participant_a_id = participant_b_id, "
            "    participant_b_id = participant_a_id "
            "WHERE CAST(participant_a_id AS TEXT) > CAST(participant_b_id AS TEXT)"
        )

    # --- 4. New pair-level integrity --------------------------------------
    op.create_unique_constraint(
        "uq_staff_conversations_participant_pair",
        "staff_conversations",
        ["participant_a_id", "participant_b_id"],
    )
    op.create_check_constraint(
        "ck_staff_conversations_distinct_participants",
        "staff_conversations",
        "participant_a_id <> participant_b_id",
    )
    op.create_index(
        "ix_staff_conversations_participant_a",
        "staff_conversations",
        ["participant_a_id"],
    )
    op.create_index(
        "ix_staff_conversations_participant_b",
        "staff_conversations",
        ["participant_b_id"],
    )

    # --- 5. Structured mentions -------------------------------------------
    op.create_table(
        "staff_message_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("mentioned_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["staff_messages.id"]),
        sa.ForeignKeyConstraint(["mentioned_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "mentioned_user_id",
            name="uq_staff_message_mentions_message_user",
        ),
    )
    op.create_index(
        "ix_staff_message_mentions_message_id",
        "staff_message_mentions",
        ["message_id"],
    )
    op.create_index(
        "ix_staff_message_mentions_mentioned_user_id",
        "staff_message_mentions",
        ["mentioned_user_id"],
    )

    op.create_table(
        "internal_message_mentions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("mentioned_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["internal_messages.id"]),
        sa.ForeignKeyConstraint(["mentioned_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "mentioned_user_id",
            name="uq_internal_message_mentions_message_user",
        ),
    )
    op.create_index(
        "ix_internal_message_mentions_message_id",
        "internal_message_mentions",
        ["message_id"],
    )
    op.create_index(
        "ix_internal_message_mentions_mentioned_user_id",
        "internal_message_mentions",
        ["mentioned_user_id"],
    )


def _downgrade_is_representable(bind) -> tuple[bool, str]:
    """Whether the current data can be represented by the legacy schema.

    Legacy invariants: every conversation includes the Owner, and no user
    appears in two conversations' ``staff_user_id`` (the old single-column
    unique index). Anything else is a *newer* conversation the old model cannot
    hold, so downgrading would fail or silently drop history.
    """
    total = (
        bind.execute(sa.text("SELECT count(*) FROM staff_conversations")).scalar() or 0
    )
    # Nothing to lose: an empty (or conversation-free) database always downgrades
    # cleanly, e.g. the disposable-DB CI job that runs against a fresh install.
    if total == 0:
        return True, ""

    owner_id = bind.execute(
        sa.text("SELECT id FROM users WHERE role::text = 'OWNER' LIMIT 1")
    ).scalar()
    if owner_id is None:
        # Conversations exist but no Owner: the legacy NOT NULL staff<->Owner
        # pair cannot represent them.
        return False, "no OWNER account exists"
    without_owner = (
        bind.execute(
            sa.text(
                "SELECT count(*) FROM staff_conversations "
                "WHERE participant_a_id <> :owner AND participant_b_id <> :owner"
            ),
            {"owner": owner_id},
        ).scalar()
        or 0
    )
    if without_owner:
        return False, (
            f"{without_owner} conversation(s) do not include the Owner; the "
            "legacy schema cannot represent them"
        )

    # Legacy staff_user_id = the non-owner participant; it must be unique.
    duplicate_staff = (
        bind.execute(
            sa.text(
                "SELECT count(*) FROM ("
                "  SELECT CASE WHEN participant_a_id = :owner "
                "              THEN participant_b_id ELSE participant_a_id END AS staff_id, "
                "         count(*) AS n "
                "  FROM staff_conversations "
                "  GROUP BY staff_id HAVING count(*) > 1"
                ") AS dupes"
            ),
            {"owner": owner_id},
        ).scalar()
        or 0
    )
    if duplicate_staff:
        return False, (
            f"{duplicate_staff} staff member(s) participate in more than one "
            "conversation; the legacy single-column unique index cannot hold that"
        )

    return True, ""


def downgrade() -> None:
    bind = op.get_bind()

    # Refuse a lossy downgrade rather than deleting history or failing halfway.
    representable, reason = _downgrade_is_representable(bind)
    if not representable:
        raise RuntimeError(
            "Cannot downgrade 0012_staff_mentions safely: "
            f"{reason}. The legacy staff<->Owner schema would lose or reject "
            "existing conversations. Refusing to downgrade."
        )

    op.drop_index(
        "ix_internal_message_mentions_mentioned_user_id",
        table_name="internal_message_mentions",
    )
    op.drop_index(
        "ix_internal_message_mentions_message_id",
        table_name="internal_message_mentions",
    )
    op.drop_table("internal_message_mentions")

    op.drop_index(
        "ix_staff_message_mentions_mentioned_user_id",
        table_name="staff_message_mentions",
    )
    op.drop_index(
        "ix_staff_message_mentions_message_id",
        table_name="staff_message_mentions",
    )
    op.drop_table("staff_message_mentions")

    op.drop_index(
        "ix_staff_conversations_participant_b", table_name="staff_conversations"
    )
    op.drop_index(
        "ix_staff_conversations_participant_a", table_name="staff_conversations"
    )
    op.drop_constraint(
        "ck_staff_conversations_distinct_participants",
        "staff_conversations",
        type_="check",
    )
    op.drop_constraint(
        "uq_staff_conversations_participant_pair",
        "staff_conversations",
        type_="unique",
    )

    # Restore the legacy orientation (staff participant in ``staff_user_id``,
    # Owner in ``owner_user_id``) so the old code reads the rows correctly, then
    # rename the columns back. Canonicalization may have put the Owner in
    # ``participant_a_id``, so swap any row where the Owner is *first*.
    owner_id = bind.execute(
        sa.text("SELECT id FROM users WHERE role::text = 'OWNER' LIMIT 1")
    ).scalar()
    if owner_id is not None:
        bind.execute(
            sa.text(
                "UPDATE staff_conversations "
                "SET participant_a_id = participant_b_id, "
                "    participant_b_id = participant_a_id "
                "WHERE participant_a_id = :owner"
            ),
            {"owner": owner_id},
        )

    op.alter_column(
        "staff_conversations",
        "participant_a_id",
        new_column_name="staff_user_id",
    )
    op.alter_column(
        "staff_conversations",
        "participant_b_id",
        new_column_name="owner_user_id",
    )
    op.create_index(
        _LEGACY_STAFF_UNIQUE_INDEX,
        "staff_conversations",
        ["staff_user_id"],
        unique=True,
    )
    op.create_index(
        _LEGACY_OWNER_INDEX,
        "staff_conversations",
        ["owner_user_id"],
    )

    # The STAFF_MENTION enum label is intentionally left in place: PostgreSQL
    # cannot remove an enum value, and the label is harmless when unused.
