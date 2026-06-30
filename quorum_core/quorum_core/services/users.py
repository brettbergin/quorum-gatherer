"""Single-human user model: one owner account that owns all chats and settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quorum_core.models import User

DEFAULT_USER_EMAIL = "owner@quorum.local"


async def get_or_create_default_user(session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.email == DEFAULT_USER_EMAIL))
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, display_name="Owner")
        session.add(user)
        await session.flush()
    return user
