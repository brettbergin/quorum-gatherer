"""User + per-user provider configuration."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quorum_core.core.db import Base
from quorum_core.models.base import TimestampMixin, gen_uuid


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))

    chats: Mapped[list[Chat]] = relationship(back_populates="user", cascade="all, delete-orphan")
    provider_settings: Mapped[list[ProviderSetting]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ProviderSetting(TimestampMixin, Base):
    """A user's configuration for one LLM provider (key stored encrypted)."""

    __tablename__ = "provider_settings"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_provider_per_user"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(40))  # anthropic, openai, google, ...
    api_key_encrypted: Mapped[str | None] = mapped_column(String(2048))
    # Council-member model + its raw reasoning knob (effort string or token budget).
    default_model: Mapped[str | None] = mapped_column(String(120))
    reasoning: Mapped[str | None] = mapped_column(String(120))
    # Chairman (synthesis) gets its own model + reasoning so it isn't downgraded with the members.
    chairman_model: Mapped[str | None] = mapped_column(String(120))
    chairman_reasoning: Mapped[str | None] = mapped_column(String(120))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="provider_settings")


# Late imports for relationship resolution.
from quorum_core.models.chat import Chat  # noqa: E402
