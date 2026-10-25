"""require a ticket number on every ticket

Revision ID: 0008_ticket_number_not_null
Revises: 0007_ticket_feedback
Create Date: 2026-10-23 00:00:00.000000

``Ticket.ticket_number`` has always been assigned by the API and is required by
``TicketRead``, but revision ``0001`` created the column as nullable. This
revision makes the database enforce the same invariant as the model and the API.

Backfill
--------
Any legacy NULL rows (there should be none on a database that only used the
application's ticket-creation service) receive consecutive numbers above the
current maximum. The unique index is respected because every generated number is
strictly greater than the existing maximum. The update is deterministic:
``created_at`` then ``id`` decides the order.

PostgreSQL-only DDL
-------------------
The project's migration target is PostgreSQL. SQLite (used by the test suite)
cannot ``ALTER COLUMN`` and builds its schema from ``SQLModel.metadata``, so this
revision intentionally skips the DDL there. On any other dialect the backfill
still runs and the DDL is attempted.

Deployment order
----------------
Deploy the application code before or together with this migration. The current
code always supplies a number, and the new model rejects a missing one, so no
request path can insert a NULL once the code is live. The migration can be run
online; it takes a brief table lock while PostgreSQL validates the column.

Downgrade only relaxes the constraint; it never removes numbers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_ticket_number_not_null"
down_revision: str | None = "0007_ticket_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIRST_TICKET_NUMBER = 10_000


def _backfill_missing_numbers() -> None:
    """Give NULL ticket numbers unique values above the current maximum."""
    # ``UPDATE ... FROM`` with a window function is supported by PostgreSQL and
    # modern SQLite (3.33+). The derived ``base`` row is a single row, so every
    # generated value is ``max_number + rn`` and cannot collide with an existing
    # number.
    op.execute(
        f"""
        WITH numbered AS (
            SELECT id,
                   ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM tickets
            WHERE ticket_number IS NULL
        ),
        base AS (
            SELECT COALESCE(MAX(ticket_number), {_FIRST_TICKET_NUMBER}) AS max_number
            FROM tickets
        )
        UPDATE tickets
        SET ticket_number = base.max_number + numbered.rn
        FROM numbered, base
        WHERE tickets.id = numbered.id
        """
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Prevent a concurrent ticket insert from racing the backfill. Without this
    # lock a transaction that computed MAX(ticket_number) before the backfill
    # could insert the same value the backfill assigns to a legacy NULL row.
    # The lock is held only for this short migration transaction.
    if bind.dialect.name == "postgresql":
        op.execute("LOCK TABLE tickets IN ACCESS EXCLUSIVE MODE")

    _backfill_missing_numbers()

    if bind.dialect.name == "sqlite":
        # SQLite cannot alter an existing column; the model metadata used by the
        # test suite already declares NOT NULL.
        return

    op.alter_column(
        "tickets",
        "ticket_number",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    op.alter_column(
        "tickets",
        "ticket_number",
        existing_type=sa.Integer(),
        nullable=True,
    )
