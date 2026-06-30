"""Editable, DB-backed council agent configuration.

Seeded from the shipped `*.agent.md` files on first boot (see `agents/seed.py`); thereafter the
desktop app reads agents from here and lets users edit prompts/frontmatter. Each row keeps an
immutable baseline of its shipped values so a user edit can be reset to default.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from quorum_core.core.db import Base
from quorum_core.models.base import TimestampMixin, gen_uuid


class AgentConfig(TimestampMixin, Base):
    __tablename__ = "agent_configs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))  # council_member | chairman
    phase: Mapped[str] = mapped_column(String(40))  # deliberation | synthesis
    default_provider: Mapped[str] = mapped_column(String(40), default="anthropic")
    default_model: Mapped[str] = mapped_column(String(120), default="claude-sonnet-4-6")
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    display_order: Mapped[int] = mapped_column(Integer, default=100)
    owned_sections: Mapped[list[str]] = mapped_column(JSON, default=list)
    output_schema: Mapped[str] = mapped_column(String(80), default="CouncilContribution")
    system_prompt: Mapped[str] = mapped_column(Text)

    # Immutable shipped baseline for "reset to default" (None for user-added agents).
    baseline_system_prompt: Mapped[str | None] = mapped_column(Text)
    baseline_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
