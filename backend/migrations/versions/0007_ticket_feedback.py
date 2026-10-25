"""notifications for resolved tickets + feedback, internal-message deep link

Revision ID: 0007_ticket_feedback
Revises: 0006_internal_messages
Create Date: 2026-10-19 00:00:00.000000

What this revision adds
-----------------------
* Three new ``notificationtype`` labels used by the notification lifecycle:
  ``TICKET_CREATED`` (the customer's receipt), ``TICKET_RESOLVED`` (the
  one-per-ticket feedback request) and ``INTERNAL_MESSAGE_RECEIVED`` (an
  Owner-composed internal message addressed to an employee).
* ``notifications.related_internal_message_id`` - an optional deep link from an
  internal-message notification to the exact ``internal_messages`` row, mirroring
  the existing ``related_conversation_id`` deep link. It is NULL for every other
  notification and never set for a customer.
* ``notifications.related_account_request_id`` - an optional deep link to the
  exact ``account_management_requests`` row, so an escalation notification opens
  the request itself instead of only its ticket.
* ``ticket_feedback`` - the customer's single rating (1-5) plus optional comment
  for a resolved ticket, with a unique ``ticket_id`` so feedback is answered at
  most once.

Nothing existing is modified: no table, column, index, constraint, or row of
``users`` / ``tickets`` / ``comments`` / ``staff_*`` /
``internal_messages`` is touched, and no existing notification's value changes.

Enum notes
----------
``ALTER TYPE public.notificationtype ADD VALUE`` runs in ``autocommit_block()``:
PostgreSQL cannot use a label added in the same transaction that added it, and
older servers cannot run it inside a transaction at all. No statement in this
migration references a newly added label, which is why the new *column and
table* can safely be created afterwards.

Downgrade
---------
Drops ``ticket_feedback`` and the ``related_internal_message_id`` column (with
its foreign key). Like ``0004``, the new ``notificationtype`` labels are left in
place: PostgreSQL cannot remove an enum value without rebuilding the shared
type, and no existing row is ever rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_ticket_feedback"
down_revision: str | None = "0006_internal_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Labels appended to the existing shared notificationtype enum.
NEW_NOTIFICATION_LABELS = (
    "TICKET_CREATED",
    "TICKET_RESOLVED",
    "INTERNAL_MESSAGE_RECEIVED",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Committed on its own; later statements never reference these labels.
        with op.get_context().autocommit_block():
            for label in NEW_NOTIFICATION_LABELS:
                op.execute(
                    f"ALTER TYPE public.notificationtype "
                    f"ADD VALUE IF NOT EXISTS '{label}'"
                )

    # --- notifications deep link -------------------------------------------
    op.add_column(
        "notifications",
        sa.Column("related_internal_message_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notifications_related_internal_message_id",
        "notifications",
        "internal_messages",
        ["related_internal_message_id"],
        ["id"],
    )

    op.add_column(
        "notifications",
        sa.Column("related_account_request_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notifications_related_account_request_id",
        "notifications",
        "account_management_requests",
        ["related_account_request_id"],
        ["id"],
    )

    # --- ticket feedback ----------------------------------------------------
    op.create_table(
        "ticket_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("customer_user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_ticket_feedback_rating_range",
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.ForeignKeyConstraint(["customer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", name="uq_ticket_feedback_ticket"),
    )


def downgrade() -> None:
    op.drop_table("ticket_feedback")

    op.drop_constraint(
        "fk_notifications_related_account_request_id",
        "notifications",
        type_="foreignkey",
    )
    op.drop_column("notifications", "related_account_request_id")

    op.drop_constraint(
        "fk_notifications_related_internal_message_id",
        "notifications",
        type_="foreignkey",
    )
    op.drop_column("notifications", "related_internal_message_id")
    # The new notificationtype labels stay (PostgreSQL cannot remove an enum
    # value without rebuilding the shared type; no row value is ever changed).
