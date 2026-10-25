"""enforce a single OWNER with a partial unique index

Revision ID: 0003_single_owner_index
Revises: 0002_owner_role
Create Date: 2026-10-18 00:00:00.000000

HelpDesk keeps exactly one permanent Owner. The database half of that rule is
a partial unique index on ``users.role`` limited to the ``OWNER`` label,
mirroring ``User.__table_args__`` in ``app/models/user.py`` (the bootstrap
command and the Owner-only user-management endpoints enforce it
transactionally on top).

This is a separate revision from ``0002_owner_role`` on purpose: the index
predicate references the ``'OWNER'`` label, and PostgreSQL forbids *using* a
value added by ``ALTER TYPE ... ADD VALUE`` in the same transaction that added
it. By the time this migration runs, ``0002_owner_role`` has committed the
label.

Deactivated Owners are still Owners, so the index is intentionally not
restricted to ``is_active``: at most one row may hold the OWNER role at all.

Downgrade simply drops the index; it never changes any user's role.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_single_owner_index"
down_revision: str | None = "0002_owner_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_single_owner "
        "ON users (role) WHERE role = 'OWNER'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS uq_users_single_owner")
