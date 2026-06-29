"""Provider configuration API.

- GET  /providers          list providers + current settings
- POST /providers/apply    validate a key (real call) then save + enable on success
- POST /providers/disable  disable a provider (keeps the stored key)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.provider import PROVIDERS, list_provider_specs
from app.agents.validation import validate_provider_key
from app.api.deps import get_current_user
from app.core.db import get_session
from app.core.security import decrypt
from app.models import ProviderSetting, User
from app.schemas.api import (
    ProviderApplyIn,
    ProviderRef,
    ProviderSettingOut,
    ProviderSpecOut,
    SettingsOut,
)
from app.services.settings_service import (
    list_provider_settings,
    upsert_provider_setting,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_out(row: ProviderSetting) -> ProviderSettingOut:
    return ProviderSettingOut(
        provider=row.provider,
        default_model=row.default_model,
        is_enabled=row.is_enabled,
        has_key=bool(row.api_key_encrypted),
    )


async def _get_setting(
    session: AsyncSession, user_id: str, provider: str
) -> ProviderSetting | None:
    return await session.scalar(
        select(ProviderSetting).where(
            ProviderSetting.user_id == user_id, ProviderSetting.provider == provider
        )
    )


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
    return SettingsOut(providers=specs, settings=[_to_out(r) for r in rows])


@router.post("/providers/apply", response_model=ProviderSettingOut)
async def apply_provider(
    body: ProviderApplyIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProviderSettingOut:
    spec = PROVIDERS.get(body.provider)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"unknown provider '{body.provider}'")

    existing = await _get_setting(session, user.id, body.provider)

    # Use the supplied key, otherwise reuse the stored one.
    key = body.api_key or (
        decrypt(existing.api_key_encrypted) if existing and existing.api_key_encrypted else None
    )
    if not key:
        raise HTTPException(status_code=400, detail="An API key is required.")

    model = (
        body.default_model or (existing.default_model if existing else None) or spec.default_model
    )

    ok, error = await validate_provider_key(body.provider, model, key)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Key validation failed: {error}")

    row = await upsert_provider_setting(
        session,
        user.id,
        body.provider,
        api_key=body.api_key or None,  # None = keep the existing encrypted key
        default_model=body.default_model,
        is_enabled=True,
    )
    await session.commit()
    return _to_out(row)


@router.post("/providers/disable", response_model=ProviderSettingOut)
async def disable_provider(
    body: ProviderRef,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProviderSettingOut:
    existing = await _get_setting(session, user.id, body.provider)
    if existing is None:
        raise HTTPException(status_code=404, detail="provider not configured")
    existing.is_enabled = False
    await session.commit()
    return _to_out(existing)
