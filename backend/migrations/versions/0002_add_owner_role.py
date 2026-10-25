"""add OWNER to the PostgreSQL role enum

Revision ID: 0002_owner_role
Revises: 0001_initial
Create Date: 2026-10-18 00:00:00.000000

Adds the fourth application role, ``OWNER``, to the existing native
PostgreSQL enum type. Inspection of the live database established that the
type is ``public.role`` and that it already contains exactly ``CUSTOMER``,
``ADMIN`` and ``AGENT`` (the SQLAlchemy enum member *names*, which is how
``sa.Enum`` stores a ``str`` enum in a native PostgreSQL enum). Existing
labels, every row, and every relationship are left untouched.

PostgreSQL details
------------------
* ``ALTER TYPE ... ADD VALUE`` cannot be used by other statements in the same
  transaction, so it runs inside Alembic's ``autocommit_block()``: the new
  label is committed on its own before the migration transaction continues.
  This is also why the partial index that *references* ``'OWNER'`` lives in
  the follow-up revision ``0003_single_owner_index`` rather than here.
* ``IF NOT EXISTS`` keeps the statement idempotent and safe to re-run.
* Non-PostgreSQL dialects (the in-memory SQLite used by the test suite) inline
  their enum values and have no standalone type to alter, so this is a no-op
  there.

Rollback
--------
PostgreSQL has no ``ALTER TYPE ... DROP VALUE``. Removing an enum label can
only be done by rebuilding the type (and every dependent column and index),
which is a destructive, data-aware operation that must be designed and
reviewed separately. This migration therefore refuses to auto-downgrade: it
never silently demotes an Owner and never rewrites shared history.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_owner_role"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Committed on its own so later statements (in this migration or the next
    # one) may reference the new label.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.role ADD VALUE IF NOT EXISTS 'OWNER'")


def downgrade() -> None:
    raise RuntimeError(
        "Cannot automatically downgrade 0002_owner_role. PostgreSQL cannot "
        "drop a single value from an enum type without rebuilding the type "
        "and every dependent column/index, and a rollback must never demote "
        "the Owner implicitly. Removing the OWNER label requires a separately "
        "reviewed, data-aware migration."
    )
