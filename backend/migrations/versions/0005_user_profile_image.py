"""add users.image_url for the Clerk-synced profile photo

Revision ID: 0005_user_profile_image
Revises: 0004_support_workflows
Create Date: 2026-10-19 00:00:00.000000

Clerk remains the source of truth for a user's profile image. This nullable
column stores the *Clerk-hosted* image URL (``user.image_url``) so that other
participants of a ticket/conversation can be rendered with their photo without
the frontend ever holding the Clerk secret. The value is only ever written from
verified Clerk data server-side (provisioning in ``app/core/auth.py`` and the
explicit ``POST /api/v1/users/me/avatar`` sync endpoint); it is never accepted
from a client request body.

Clients can remove their own photo through Clerk (Clerk then serves its default
image), in which case this column is refreshed to whatever Clerk reports.

Downgrade simply drops the column; it never modifies any other user field and
never touches the Owner's identity.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_user_profile_image"
down_revision: str | None = "0004_support_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("image_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "image_url")
