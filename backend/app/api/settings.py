"""Provider configuration API.

- GET  /providers          list providers + current settings
- POST /providers/models   fetch a provider's live model catalog (also validates the key)
- POST /providers/apply    validate a key (real call) then save + enable on success
- POST /providers/disable  disable a provider (keeps the stored key)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from quorum_core.agents.catalog import CatalogError
from quorum_core.agents.provider import ProviderError, list_provider_specs
from quorum_core.core.db import get_session
from quorum_core.models import ProviderSetting, User
from quorum_core.services.settings_service import (
    apply_provider as svc_apply_provider,
)
from quorum_core.services.settings_service import (
    disable_provider as svc_disable_provider,
)
from quorum_core.services.settings_service import (
    fetch_provider_models as svc_fetch_provider_models,
)
from quorum_core.services.settings_service import (
    list_provider_settings,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.schemas.api import (
    ModelCatalogOut,
    ModelInfoOut,
    ProviderApplyIn,
    ProviderModelsIn,
    ProviderRef,
    ProviderSettingOut,
    ProviderSpecOut,
    ReasoningSpecOut,
    SettingsOut,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_out(row: ProviderSetting) -> ProviderSettingOut:
    return ProviderSettingOut(
        provider=row.provider,
        default_model=row.default_model,
        reasoning=row.reasoning,
        chairman_model=row.chairman_model,
        chairman_reasoning=row.chairman_reasoning,
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
            reasoning=ReasoningSpecOut(
                kind=s.reasoning.kind,
                settings_key=s.reasoning.settings_key,
                efforts=list(s.reasoning.efforts),
                budget_min=s.reasoning.budget_min,
                budget_max=s.reasoning.budget_max,
                budget_default=s.reasoning.budget_default,
                model_pattern=s.reasoning.model_pattern,
            ),
        )
        for s in list_provider_specs()
    ]
    rows = await list_provider_settings(session, user.id)
    return SettingsOut(providers=specs, settings=[_to_out(r) for r in rows])


@router.post("/providers/models", response_model=ModelCatalogOut)
async def fetch_provider_models(
    body: ProviderModelsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ModelCatalogOut:
    try:
        models = await svc_fetch_provider_models(
            session, user.id, body.provider, api_key=body.api_key
        )
    except CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ModelCatalogOut(models=[ModelInfoOut(**m) for m in models])


@router.post("/providers/apply", response_model=ProviderSettingOut)
async def apply_provider(
    body: ProviderApplyIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProviderSettingOut:
    ok, error = await svc_apply_provider(
        session,
        user.id,
        body.provider,
        api_key=body.api_key,
        default_model=body.default_model,
        reasoning=body.reasoning,
        chairman_model=body.chairman_model,
        chairman_reasoning=body.chairman_reasoning,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=error or "could not enable provider")
    await session.commit()
    row = await _get_setting(session, user.id, body.provider)
    if row is None:
        raise HTTPException(status_code=404, detail="provider not configured")
    return _to_out(row)


@router.post("/providers/disable", response_model=ProviderSettingOut)
async def disable_provider(
    body: ProviderRef,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProviderSettingOut:
    if not await svc_disable_provider(session, user.id, body.provider):
        raise HTTPException(status_code=404, detail="provider not configured")
    await session.commit()
    row = await _get_setting(session, user.id, body.provider)
    if row is None:
        raise HTTPException(status_code=404, detail="provider not configured")
    return _to_out(row)
