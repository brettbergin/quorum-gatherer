"""The Chairman's final synthesis for a chat (the full Output Format document)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, gen_uuid


class CouncilReport(TimestampMixin, Base):
    __tablename__ = "council_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), unique=True)
    # Full structured Output Format (executive summary, perspectives, assumptions,
    # alternatives, stress test, investment review, decision classification, MVP,
    # validation, metrics, kill criteria, tensions, final recommendation).
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    markdown: Mapped[str | None] = mapped_column(Text)  # rendered convenience copy

    chat: Mapped[Chat] = relationship(back_populates="report")


# Late import for relationship resolution.
from app.models.chat import Chat  # noqa: E402
