"""initial schema

Creates every table used by the HelpDesk backend, matching
``app.models`` / ``SQLModel.metadata``.

Notes for reviewers:

* Enum columns use the *member names* as their database labels
  (``CUSTOMER``/``ADMIN``/``AGENT``, ``OPEN``/``IN_PROGRESS``/...). This is how
  SQLAlchemy already stores them, so the migration deliberately keeps uppercase
  labels even though the JSON API exposes lowercase role values.
* PostgreSQL native enum types (``role``, ``ticketstatus``, ``ticketpriority``,
  ``notificationtype``) are created together with the tables and dropped
  explicitly in ``downgrade``.

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Native enum types. Labels are the Python enum member names.
role_enum = sa.Enum("CUSTOMER", "ADMIN", "AGENT", name="role")
ticket_status_enum = sa.Enum(
    "OPEN",
    "IN_PROGRESS",
    "WAITING_ON_CUSTOMER",
    "RESOLVED",
    "CLOSED",
    name="ticketstatus",
)
ticket_priority_enum = sa.Enum("LOW", "NORMAL", "HIGH", "URGENT", name="ticketpriority")
notification_type_enum = sa.Enum(
    "TICKET_ASSIGNED",
    "NEW_COMMENT",
    "STATUS_CHANGED",
    "PRIORITY_CHANGED",
    name="notificationtype",
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_id", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("username", sa.String(length=90), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            role_enum,
            server_default=sa.text("'CUSTOMER'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
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
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_clerk_id", "users", ["clerk_id"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_number", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status",
            ticket_status_enum,
            server_default=sa.text("'OPEN'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            ticket_priority_enum,
            server_default=sa.text("'NORMAL'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tickets_assignee_user_id", "tickets", ["assignee_user_id"])
    op.create_index("ix_tickets_created_by_user_id", "tickets", ["created_by_user_id"])
    op.create_index(
        "ix_tickets_ticket_number", "tickets", ["ticket_number"], unique=True
    )

    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_attachments_storage_key"),
    )
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "is_internal",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("related_ticket_id", sa.Uuid(), nullable=True),
        sa.Column("type", notification_type_enum, nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column(
            "is_read",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["related_ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_recipient_user_id",
        "notifications",
        ["recipient_user_id"],
    )

    op.create_table(
        "ticket_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_history_ticket_id", "ticket_history", ["ticket_id"])


def downgrade() -> None:
    # WARNING: this drops every table and therefore all of their data. It is
    # safe to run on a disposable database, but no data is preserved. Do not
    # run it against a production database without a verified backup.
    op.drop_index("ix_ticket_history_ticket_id", table_name="ticket_history")
    op.drop_table("ticket_history")

    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_comments_ticket_id", table_name="comments")
    op.drop_table("comments")

    op.drop_index("ix_attachments_ticket_id", table_name="attachments")
    op.drop_table("attachments")

    op.drop_index("ix_tickets_ticket_number", table_name="tickets")
    op.drop_index("ix_tickets_created_by_user_id", table_name="tickets")
    op.drop_index("ix_tickets_assignee_user_id", table_name="tickets")
    op.drop_table("tickets")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_clerk_id", table_name="users")
    op.drop_table("users")

    # Drop the PostgreSQL enum types explicitly; op.drop_table leaves them
    # behind. Other dialects (e.g. SQLite) inline the enum and have nothing to
    # drop.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="notificationtype").drop(bind, checkfirst=True)
        sa.Enum(name="ticketpriority").drop(bind, checkfirst=True)
        sa.Enum(name="ticketstatus").drop(bind, checkfirst=True)
        sa.Enum(name="role").drop(bind, checkfirst=True)
