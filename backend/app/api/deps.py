"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends
from quorum_core.core.db import get_session
from quorum_core.models import User
from quorum_core.services.users import get_or_create_default_user
from sqlalchemy.ext.asyncio import AsyncSession


async def get_current_user(session: AsyncSession = Depends(get_session)) -> User:
    """Single-human model: resolve (or create) the one owner account."""
    user = await get_or_create_default_user(session)
    await session.commit()
    return user
