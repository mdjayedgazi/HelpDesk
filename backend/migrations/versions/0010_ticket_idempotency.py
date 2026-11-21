"""add ticket create idempotency key

Revision ID: 0010_ticket_idempotency
Revises: 0009_attachment_scan_status
Create Date: 2026-11-21 00:00:00.000000

A client may send an ``Idempotency-Key`` header on ticket creation. The
optional column and the partial unique index make a retried or double-submitted
request return the original ticket instead of opening a duplicate.

Existing rows keep ``NULL`` and are unaffected because the unique index ignores
``NULL`` keys (PostgreSQL and SQLite both treat NULLs as distinct in a unique
index). The index is per creator, so two customers may independently use the
same key value.

The index is not created concurrently: the tickets table is support-desk sized.
On a very large table, create the equivalent ``CREATE UNIQUE INDEX
CONCURRENTLY`` first and mark this revision accordingly.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_ticket_idempotency"
down_revision: str | None = "0009_attachment_scan_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "uq_tickets_creator_request_key"
_NOT_NULL = sa.text("client_request_id IS NOT NULL")


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("client_request_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        _INDEX_NAME,
        "tickets",
        ["created_by_user_id", "client_request_id"],
        unique=True,
        postgresql_where=_NOT_NULL,
        sqlite_where=_NOT_NULL,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="tickets")
    op.drop_column("tickets", "client_request_id")
