"""add attachment malware-scan status

Revision ID: 0009_attachment_scan_status
Revises: 0008_ticket_number_not_null
Create Date: 2026-10-24 00:00:00.000000

Existing attachments were accepted before a malware scanner existed. They are
marked ``PENDING`` and are **not downloadable** until an operator runs the
rescan command. This migration never labels unscanned files as clean.

New uploads are scanned synchronously in quarantine and stored as ``CLEAN``;
infected or unscannable files are deleted before a row is created.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_attachment_scan_status"
down_revision: str | None = "0008_ticket_number_not_null"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``create_type=False`` keeps SQLAlchemy from emitting duplicate CREATE TYPE
# statements; the type is created explicitly below on PostgreSQL.
attachment_scan_status_enum = sa.Enum(
    "PENDING",
    "CLEAN",
    "INFECTED",
    name="attachmentscanstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        attachment_scan_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "attachments",
        sa.Column(
            "scan_status",
            attachment_scan_status_enum,
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column("attachments", "scan_status")
    if bind.dialect.name == "postgresql":
        attachment_scan_status_enum.drop(bind, checkfirst=True)
