"""A single agent's run within a chat (one council member or the Chairman)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, gen_uuid
from app.models.enums import AgentRunPhase, AgentRunStatus


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))

    agent_key: Mapped[str] = mapped_column(String(80))
    agent_name: Mapped[str] = mapped_column(String(120))
    phase: Mapped[AgentRunPhase] = mapped_column(
        SAEnum(AgentRunPhase, native_enum=False, length=20)
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(AgentRunStatus, native_enum=False, length=20), default=AgentRunStatus.pending
    )

    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(120))

    input_text: Mapped[str | None] = mapped_column(Text)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # structured contribution
    output_text: Mapped[str | None] = mapped_column(Text)  # streamed/raw text
    error: Mapped[str | None] = mapped_column(Text)

    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    chat: Mapped[Chat] = relationship(back_populates="agent_runs")


# Late import for relationship resolution.
from app.models.chat import Chat  # noqa: E402
