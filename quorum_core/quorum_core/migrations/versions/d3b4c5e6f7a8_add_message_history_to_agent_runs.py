"""add message_history to agent_runs

Revision ID: d3b4c5e6f7a8
Revises: c2a3b4d5e6f7
Create Date: 2026-06-29 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3b4c5e6f7a8"
down_revision: str | None = "c2a3b4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("message_history", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "message_history")
