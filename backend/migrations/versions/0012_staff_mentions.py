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

Safety
------
No row is deleted, no message body is touched, and the canonical normalization
cannot collide: the old ``staff_user_id`` unique index guarantees distinct
staff participants, so two rows can never canonicalize to the same pair. On
PostgreSQL the new enum label is added in an ``autocommit_block`` (it cannot run
inside Alembic's transaction). Downgrade restores the column names and drops the
new objects; the participant ordering is left canonical (a lossless state that
the old code reads correctly).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_staff_mentions"
down_revision: str | None = "0011_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    if is_postgresql:
        # New notification label, committed on its own.
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE public.notificationtype "
                "ADD VALUE IF NOT EXISTS 'STAFF_MENTION'"
            )

    # --- generalize the participant columns --------------------------------
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

    # Canonical order: smaller UUID first. PostgreSQL compares UUIDs natively;
    # on other dialects the cast to text is equivalent and total.
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

    # Drop the old single-participant indexes, then add the pair constraint.
    op.drop_index("uq_staff_conversations_staff_user", table_name="staff_conversations")
    op.drop_index(
        "ix_staff_conversations_owner_user_id", table_name="staff_conversations"
    )

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

    # --- structured mentions ----------------------------------------------
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


def downgrade() -> None:
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
        "uq_staff_conversations_staff_user",
        "staff_conversations",
        ["staff_user_id"],
        unique=True,
    )
    op.create_index(
        "ix_staff_conversations_owner_user_id",
        "staff_conversations",
        ["owner_user_id"],
    )

    # The STAFF_MENTION enum label is intentionally left in place: PostgreSQL
    # cannot remove an enum value, and the label is harmless when unused.
