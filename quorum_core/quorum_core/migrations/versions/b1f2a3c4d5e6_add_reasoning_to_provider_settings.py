"""add reasoning to provider_settings

Revision ID: b1f2a3c4d5e6
Revises: c93d15e6f617
Create Date: 2026-06-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1f2a3c4d5e6"
down_revision: str | None = "c93d15e6f617"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_settings",
        sa.Column("reasoning", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_settings", "reasoning")
