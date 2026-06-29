"""Per-user provider settings: CRUD with API keys encrypted at rest, plus the
`configured` map consumed by the model resolver."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.provider import PROVIDERS, ProviderError
from app.core.security import decrypt, encrypt
from app.models import ProviderSetting


async def list_provider_settings(session: AsyncSession, user_id: str) -> list[ProviderSetting]:
    rows = await session.scalars(select(ProviderSetting).where(ProviderSetting.user_id == user_id))
    return list(rows)


async def upsert_provider_setting(
    session: AsyncSession,
    user_id: str,
    provider: str,
    *,
    api_key: str | None = None,
    default_model: str | None = None,
    is_enabled: bool = True,
) -> ProviderSetting:
    if provider not in PROVIDERS:
        raise ProviderError(f"unknown provider '{provider}'; known: {sorted(PROVIDERS)}")

    existing = await session.scalar(
        select(ProviderSetting).where(
            ProviderSetting.user_id == user_id,
            ProviderSetting.provider == provider,
        )
    )
    if existing is None:
        existing = ProviderSetting(user_id=user_id, provider=provider)
        session.add(existing)

    # api_key: None means "leave unchanged"; empty string means "clear".
    if api_key is not None:
        existing.api_key_encrypted = encrypt(api_key) if api_key else None
    if default_model is not None:
        existing.default_model = default_model or None
    existing.is_enabled = is_enabled

    await session.flush()
    return existing


async def build_configured_providers(session: AsyncSession, user_id: str) -> dict[str, dict]:
    """provider -> {api_key (decrypted), default_model, enabled} for the model resolver."""
    out: dict[str, dict] = {}
    for row in await list_provider_settings(session, user_id):
        out[row.provider] = {
            "api_key": decrypt(row.api_key_encrypted) if row.api_key_encrypted else None,
            "default_model": row.default_model,
            "enabled": row.is_enabled,
        }
    return out
