"""Chat session, uploaded context documents, and chat messages."""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, gen_uuid
from app.models.enums import ChatStatus, MessageAuthorType


class Chat(TimestampMixin, Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String(300))
    idea: Mapped[str | None] = mapped_column(Text)  # the strategy idea/question
    status: Mapped[ChatStatus] = mapped_column(
        SAEnum(ChatStatus, native_enum=False, length=20), default=ChatStatus.created
    )

    user: Mapped[User] = relationship(back_populates="chats")
    documents: Mapped[list[ChatDocument]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="chat", cascade="all, delete-orphan"
    )
    report: Mapped[CouncilReport | None] = relationship(
        back_populates="chat", cascade="all, delete-orphan", uselist=False
    )


class ChatDocument(TimestampMixin, Base):
    """Authoritative context uploaded to a chat (persona, JTBD, strategy, …)."""

    __tablename__ = "chat_documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)  # extracted text injected into agents

    chat: Mapped[Chat] = relationship(back_populates="documents")


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    author_type: Mapped[MessageAuthorType] = mapped_column(
        SAEnum(MessageAuthorType, native_enum=False, length=20)
    )
    author_key: Mapped[str | None] = mapped_column(String(80))  # agent key, or None
    content: Mapped[str] = mapped_column(Text)

    chat: Mapped[Chat] = relationship(back_populates="messages")


# Late imports for relationship resolution.
from app.models.report import CouncilReport  # noqa: E402
from app.models.run import AgentRun  # noqa: E402
from app.models.user import User  # noqa: E402
