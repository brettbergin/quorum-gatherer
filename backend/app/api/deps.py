"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import User
from app.services.users import get_or_create_default_user


async def get_current_user(session: AsyncSession = Depends(get_session)) -> User:
    """Single-human model: resolve (or create) the one owner account."""
    user = await get_or_create_default_user(session)
    await session.commit()
    return user
