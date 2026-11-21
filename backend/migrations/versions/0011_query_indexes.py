"""add indexes for ticket and notification list ordering

Revision ID: 0011_query_indexes
Revises: 0010_ticket_idempotency
Create Date: 2026-11-21 00:00:00.000000

Two additive, non-unique indexes for query shapes the API already runs. Each
was chosen from an actual query, not added speculatively, and neither
duplicates an existing index:

* ``ix_tickets_created_at`` - every ticket list (admin, agent queue, customer)
  filters by role then orders by ``created_at DESC`` with ``LIMIT/OFFSET``.
  ``0001`` indexed the role columns but not ``created_at``, so the default
  listing sorted the whole table. This index serves the ordering and the
  newest-first pagination.
* ``ix_notifications_recipient_created_at`` - the notification panel lists one
  recipient's rows ordered by ``created_at DESC`` and the unread count filters
  ``recipient_user_id`` + ``is_read``. The existing single-column recipient
  index cannot satisfy the ordering. The composite's leading column still
  serves plain recipient lookups, and the ``recipient_user_id`` index is kept
  (they are not identical indexes).

The indexes are not created concurrently: the tables are support-desk sized. On
a very large table, create the equivalents with ``CREATE INDEX CONCURRENTLY``
first. This revision must not be applied twice.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_query_indexes"
down_revision: str | None = "0010_ticket_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_tickets_created_at", "tickets", ["created_at"]),
    (
        "ix_notifications_recipient_created_at",
        "notifications",
        ["recipient_user_id", "created_at"],
    ),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
