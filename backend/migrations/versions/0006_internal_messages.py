"""owner inbox: internal messages (broadcasts and direct notes)

Revision ID: 0006_internal_messages
Revises: 0005_user_profile_image
Create Date: 2026-10-19 00:00:00.000000

What this revision adds
-----------------------
* A new native ``internalaudience`` enum type with the four Owner compose
  options (``EVERYONE`` / ``AGENTS`` / ``ADMINS`` / ``INDIVIDUAL``).
* ``internal_messages`` - an Owner-composed message. A group message is stored
  exactly once; ``recipient_count`` snapshots how many employees it addressed.
* ``internal_message_recipients`` - one row per addressed employee, with
  identity snapshots (name/email/role) taken at send time and a per-recipient
  ``read_at``. This is what preserves the intended recipient list even after a
  role change, and what makes the "read" count in the Sent view real.

Nothing existing is modified: no table, column, index, constraint, or row of
``users`` / ``tickets`` / ``comments`` / ``notifications`` / ``staff_*`` is
touched. The pre-existing ``staff_conversations`` / ``staff_messages`` channel
(the 1:1 staff <-> Owner thread) is left exactly as it is.

Enum notes
----------
``internalaudience`` is created exactly once, explicitly, with
``checkfirst=True`` and ``create_type=False`` on the column so the table DDL
never attempts to create the type itself (mirrors ``0004_support_workflows``).
The ``role`` type used by the recipient role snapshot already exists
(``0001`` + ``0002``), so that column likewise declares ``create_type=False``
and the migration never recreates it. On other dialects (the in-memory SQLite
used by the unit tests, which never runs migrations) ``sa.Enum`` inlines its
values and the explicit ``CREATE TYPE`` is skipped.

Downgrade
---------
Drops the two new tables, their indexes and the new ``internalaudience`` enum
type. It never touches the existing ``role`` type or any pre-existing row.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_internal_messages"
down_revision: Union[str, None] = "0005_user_profile_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ``create_type=False`` keeps the enum DDL out of the table definitions; the
# project-owned type is created exactly once, explicitly, below.
internal_audience_enum = sa.Enum(
    "EVERYONE",
    "AGENTS",
    "ADMINS",
    "INDIVIDUAL",
    name="internalaudience",
    create_type=False,
)

# The recipient role snapshot reuses the existing native ``role`` type. It is
# never created or dropped here (``create_type=False``), matching the four
# labels established by ``0001_initial`` and ``0002_owner_role``.
role_enum = sa.Enum(
    "CUSTOMER",
    "ADMIN",
    "AGENT",
    "OWNER",
    name="role",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        internal_audience_enum.create(bind, checkfirst=True)

    op.create_table(
        "internal_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("audience", internal_audience_enum, nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(subject) > 0",
            name="ck_internal_messages_subject_nonempty",
        ),
        sa.CheckConstraint(
            "length(body) > 0",
            name="ck_internal_messages_body_nonempty",
        ),
        sa.CheckConstraint(
            "recipient_count > 0",
            name="ck_internal_messages_recipient_count_positive",
        ),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_internal_messages_sender_user_id",
        "internal_messages",
        ["sender_user_id"],
    )
    op.create_index(
        "ix_internal_messages_audience", "internal_messages", ["audience"]
    )
    op.create_index(
        "ix_internal_messages_created_at", "internal_messages", ["created_at"]
    )

    op.create_table(
        "internal_message_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_role_snapshot", role_enum, nullable=False),
        sa.Column(
            "recipient_full_name_snapshot",
            sa.String(length=120),
            nullable=False,
        ),
        sa.Column(
            "recipient_email_snapshot",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["internal_messages.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "recipient_user_id",
            name="uq_internal_message_recipients_message_user",
        ),
    )
    op.create_index(
        "ix_internal_message_recipients_message_id",
        "internal_message_recipients",
        ["message_id"],
    )
    op.create_index(
        "ix_internal_message_recipients_recipient_user_id",
        "internal_message_recipients",
        ["recipient_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_internal_message_recipients_recipient_user_id",
        table_name="internal_message_recipients",
    )
    op.drop_index(
        "ix_internal_message_recipients_message_id",
        table_name="internal_message_recipients",
    )
    op.drop_table("internal_message_recipients")

    op.drop_index(
        "ix_internal_messages_created_at", table_name="internal_messages"
    )
    op.drop_index(
        "ix_internal_messages_audience", table_name="internal_messages"
    )
    op.drop_index(
        "ix_internal_messages_sender_user_id", table_name="internal_messages"
    )
    op.drop_table("internal_messages")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        internal_audience_enum.drop(bind, checkfirst=True)
