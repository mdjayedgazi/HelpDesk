"""support workflows: categories, contact phone, auto-assignment, staff
messaging, and account-management requests

Revision ID: 0004_support_workflows
Revises: 0003_single_owner_index
Create Date: 2026-10-18 00:00:00.000000

What this revision adds
-----------------------
* ``tickets.category`` (native ``ticketcategory`` enum), required by the
  intake API, with ``'OTHER'`` as the server default so pre-existing tickets
  stay valid and readable.
* ``tickets.contact_phone`` (nullable) - optional PII, never returned by the
  public ticket schema.
* ``tickets.assigned_at`` (nullable timestamptz) - written together with the
  assignee; drives the fairness tie-break of the automatic assignment service.
* Native ``escalationstatus`` and ``escalationcategory`` enum types plus the
  five new ``notificationtype`` labels used by the new workflows.
* ``staff_conversations`` / ``staff_messages`` - the private staff <-> Owner
  channel (deliberately separate from ticket comments).
* ``notifications.related_conversation_id`` - deep link for private-message
  notifications (always NULL for customer notifications).
* ``account_management_requests`` and its comment/event tables - the audited
  escalation workflow. No identity fields are stored or mutated here.

Enum notes
----------
The three new PostgreSQL types are declared with ``create_type=False`` so the
column/table DDL never attempts to create them, then created exactly once by
``Enum.create(bind, checkfirst=True)`` so the migration is re-runnable. On
other dialects (the in-memory SQLite used by the unit tests, which never runs
migrations) ``sa.Enum`` inlines its values and the explicit ``CREATE TYPE``
blocks are skipped.

``ALTER TYPE ... ADD VALUE`` runs in ``autocommit_block()``: PostgreSQL cannot
use a label added in the same transaction that added it, and older servers
cannot run it inside a transaction at all. No statement in this migration
references a newly added ``notificationtype`` label, which is also why the
new *columns/tables* can safely be created afterwards.

Downgrade
---------
Drops the new tables, columns, indexes, and the three new enum types (the
project-owned ``ticketcategory``/``escalation*`` types are dropped only after
every dependent column/table is gone). The five ``notificationtype`` labels
cannot be removed by PostgreSQL without rebuilding the shared type, so - like
``0002_owner_role`` - they are intentionally left in place; no existing row's
value is ever modified.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_support_workflows"
down_revision: str | None = "0003_single_owner_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ``create_type=False`` keeps the enum DDL out of ``op.add_column`` /
# ``op.create_table``: the types are created exactly once, explicitly, by
# ``Enum.create(bind, checkfirst=True)`` below (year 2026 SQLAlchemy emits
# ``CREATE TYPE`` automatically for table DDL otherwise, which made the
# migration fail with ``DuplicateObject``).
ticket_category_enum = sa.Enum(
    "BILLING",
    "ACCOUNT_ACCESS",
    "TECHNICAL",
    "OUTAGE",
    "BUG",
    "ACCOUNT_MANAGEMENT",
    "OTHER",
    name="ticketcategory",
    create_type=False,
)

escalation_status_enum = sa.Enum(
    "PENDING",
    "IN_REVIEW",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
    name="escalationstatus",
    create_type=False,
)

escalation_category_enum = sa.Enum(
    "ACCOUNT_RECOVERY",
    "IDENTITY_LINKING",
    "PROFILE_CORRECTION",
    "ROLE_OR_STATUS_CHANGE",
    "OTHER",
    name="escalationcategory",
    create_type=False,
)

# Labels appended to the existing shared notificationtype enum.
NEW_NOTIFICATION_LABELS = (
    "TICKET_NEEDS_ASSIGNMENT",
    "STAFF_MESSAGE_RECEIVED",
    "OWNER_MESSAGE_RECEIVED",
    "ESCALATION_CREATED",
    "ESCALATION_UPDATED",
)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"

    if is_postgresql:
        ticket_category_enum.create(bind, checkfirst=True)
        escalation_status_enum.create(bind, checkfirst=True)
        escalation_category_enum.create(bind, checkfirst=True)
        # Committed on its own; later statements never reference these labels.
        with op.get_context().autocommit_block():
            for label in NEW_NOTIFICATION_LABELS:
                op.execute(
                    f"ALTER TYPE public.notificationtype "
                    f"ADD VALUE IF NOT EXISTS '{label}'"
                )

    # --- tickets -----------------------------------------------------------
    op.add_column(
        "tickets",
        sa.Column(
            "category",
            ticket_category_enum,
            server_default=sa.text("'OTHER'"),
            nullable=False,
        ),
    )
    op.add_column(
        "tickets",
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- private staff <-> Owner messaging ---------------------------------
    op.create_table(
        "staff_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("staff_user_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["staff_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
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

    op.create_table(
        "staff_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(body) > 0", name="ck_staff_messages_body_nonempty"),
        sa.ForeignKeyConstraint(["conversation_id"], ["staff_conversations.id"]),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_staff_messages_conversation_id", "staff_messages", ["conversation_id"]
    )
    op.create_index(
        "ix_staff_messages_sender_user_id", "staff_messages", ["sender_user_id"]
    )

    # --- notifications deep link -------------------------------------------
    op.add_column(
        "notifications",
        sa.Column("related_conversation_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notifications_related_conversation_id",
        "notifications",
        "staff_conversations",
        ["related_conversation_id"],
        ["id"],
    )

    # --- account-management (escalation) requests --------------------------
    op.create_table(
        "account_management_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_full_name_snapshot", sa.String(length=120), nullable=False),
        sa.Column("target_email_snapshot", sa.String(length=255), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("category", escalation_category_enum, nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("internal_details", sa.Text(), nullable=True),
        sa.Column(
            "status",
            escalation_status_enum,
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("decision_reason", sa.String(length=2000), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_account_management_requests_target_user_id",
        "account_management_requests",
        ["target_user_id"],
    )
    op.create_index(
        "ix_account_management_requests_created_by_user_id",
        "account_management_requests",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_account_management_requests_status",
        "account_management_requests",
        ["status"],
    )
    op.create_index(
        "ix_account_management_requests_ticket_id",
        "account_management_requests",
        ["ticket_id"],
    )

    op.create_table(
        "account_management_request_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(body) > 0",
            name="ck_account_request_comments_body_nonempty",
        ),
        sa.ForeignKeyConstraint(["request_id"], ["account_management_requests.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_account_management_request_comments_request_id",
        "account_management_request_comments",
        ["request_id"],
    )

    op.create_table(
        "account_management_request_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["request_id"], ["account_management_requests.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_account_management_request_events_request_id",
        "account_management_request_events",
        ["request_id"],
    )


def downgrade() -> None:
    # Reverse order of creation so foreign keys always point at existing
    # tables. No existing row is modified.
    op.drop_index(
        "ix_account_management_request_events_request_id",
        table_name="account_management_request_events",
    )
    op.drop_table("account_management_request_events")

    op.drop_index(
        "ix_account_management_request_comments_request_id",
        table_name="account_management_request_comments",
    )
    op.drop_table("account_management_request_comments")

    op.drop_index(
        "ix_account_management_requests_ticket_id",
        table_name="account_management_requests",
    )
    op.drop_index(
        "ix_account_management_requests_status",
        table_name="account_management_requests",
    )
    op.drop_index(
        "ix_account_management_requests_created_by_user_id",
        table_name="account_management_requests",
    )
    op.drop_index(
        "ix_account_management_requests_target_user_id",
        table_name="account_management_requests",
    )
    op.drop_table("account_management_requests")

    op.drop_constraint(
        "fk_notifications_related_conversation_id",
        "notifications",
        type_="foreignkey",
    )
    op.drop_column("notifications", "related_conversation_id")

    op.drop_index("ix_staff_messages_sender_user_id", table_name="staff_messages")
    op.drop_index("ix_staff_messages_conversation_id", table_name="staff_messages")
    op.drop_table("staff_messages")

    op.drop_index(
        "ix_staff_conversations_owner_user_id", table_name="staff_conversations"
    )
    op.drop_index("uq_staff_conversations_staff_user", table_name="staff_conversations")
    op.drop_table("staff_conversations")

    op.drop_column("tickets", "assigned_at")
    op.drop_column("tickets", "contact_phone")
    op.drop_column("tickets", "category")

    # Drop the project-owned enum types now that every dependent column and
    # table is gone. The shared ``notificationtype`` labels stay (PostgreSQL
    # cannot drop enum values without rebuilding the type).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        escalation_category_enum.drop(bind, checkfirst=True)
        escalation_status_enum.drop(bind, checkfirst=True)
        ticket_category_enum.drop(bind, checkfirst=True)
