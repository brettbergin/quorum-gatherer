"""add chairman_model + chairman_reasoning to provider_settings

Revision ID: c2a3b4d5e6f7
Revises: b1f2a3c4d5e6
Create Date: 2026-06-29 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2a3b4d5e6f7"
down_revision: str | None = "b1f2a3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_settings",
        sa.Column("chairman_model", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "provider_settings",
        sa.Column("chairman_reasoning", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_settings", "chairman_reasoning")
    op.drop_column("provider_settings", "chairman_model")
