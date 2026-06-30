"""add agent_configs table + chats.active_agents

Revision ID: e4c5d6f7a8b9
Revises: d3b4c5e6f7a8
Create Date: 2026-06-29 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4c5d6f7a8b9"
down_revision: str | None = "d3b4c5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("phase", sa.String(length=40), nullable=False),
        sa.Column("default_provider", sa.String(length=40), nullable=False),
        sa.Column("default_model", sa.String(length=120), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("owned_sections", sa.JSON(), nullable=True),
        sa.Column("output_schema", sa.String(length=80), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("baseline_system_prompt", sa.Text(), nullable=True),
        sa.Column("baseline_meta", sa.JSON(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_configs_key", "agent_configs", ["key"], unique=True)
    op.add_column("chats", sa.Column("active_agents", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chats", "active_agents")
    op.drop_index("ix_agent_configs_key", table_name="agent_configs")
    op.drop_table("agent_configs")
