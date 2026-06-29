"""Provider configuration API — list providers + current settings, and upsert one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.provider import ProviderError, list_provider_specs
from app.api.deps import get_current_user
from app.core.db import get_session
from app.models import User
from app.schemas.api import (
    ProviderSettingIn,
    ProviderSettingOut,
    ProviderSpecOut,
    SettingsOut,
)
from app.services.settings_service import (
    list_provider_settings,
    upsert_provider_setting,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/providers", response_model=SettingsOut)
async def get_providers(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SettingsOut:
    specs = [
        ProviderSpecOut(
            key=s.key,
            label=s.label,
            default_model=s.default_model,
            suggested_models=list(s.suggested_models),
        )
        for s in list_provider_specs()
    ]
    rows = await list_provider_settings(session, user.id)
    settings = [
        ProviderSettingOut(
            provider=r.provider,
            default_model=r.default_model,
            is_enabled=r.is_enabled,
            has_key=bool(r.api_key_encrypted),
        )
        for r in rows
    ]
    return SettingsOut(providers=specs, settings=settings)


@router.put("/providers", response_model=ProviderSettingOut)
async def put_provider(
    body: ProviderSettingIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProviderSettingOut:
    try:
        row = await upsert_provider_setting(
            session,
            user.id,
            body.provider,
            api_key=body.api_key,
            default_model=body.default_model,
            is_enabled=body.is_enabled,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return ProviderSettingOut(
        provider=row.provider,
        default_model=row.default_model,
        is_enabled=row.is_enabled,
        has_key=bool(row.api_key_encrypted),
    )
