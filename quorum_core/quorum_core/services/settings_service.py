"""Per-user provider settings: CRUD with API keys encrypted at rest, plus the
`configured` map consumed by the model resolver."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quorum_core.agents.catalog import ModelInfo, fetch_models
from quorum_core.agents.provider import PROVIDERS, ProviderError
from quorum_core.agents.validation import validate_provider_key
from quorum_core.core.security import decrypt, encrypt
from quorum_core.models import ProviderSetting


async def _get(session: AsyncSession, user_id: str, provider: str) -> ProviderSetting | None:
    return await session.scalar(
        select(ProviderSetting).where(
            ProviderSetting.user_id == user_id, ProviderSetting.provider == provider
        )
    )


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
    reasoning: str | None = None,
    chairman_model: str | None = None,
    chairman_reasoning: str | None = None,
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

    # Each field: None means "leave unchanged"; empty string means "clear".
    if api_key is not None:
        existing.api_key_encrypted = encrypt(api_key) if api_key else None
    if default_model is not None:
        existing.default_model = default_model or None
    if reasoning is not None:
        existing.reasoning = reasoning or None
    if chairman_model is not None:
        existing.chairman_model = chairman_model or None
    if chairman_reasoning is not None:
        existing.chairman_reasoning = chairman_reasoning or None
    existing.is_enabled = is_enabled

    await session.flush()
    return existing


async def apply_provider(
    session: AsyncSession,
    user_id: str,
    provider: str,
    *,
    api_key: str | None = None,
    default_model: str | None = None,
    reasoning: str | None = None,
    chairman_model: str | None = None,
    chairman_reasoning: str | None = None,
) -> tuple[bool, str | None]:
    """Validate the key (real call) and, on success, save + enable. Flushes; caller commits.

    Shared by the web API and the desktop app so both behave identically. `api_key` blank
    reuses the stored key. `default_model`/`reasoning` are the council-member values;
    `chairman_model`/`chairman_reasoning` configure the synthesis agent independently.
    """
    if provider not in PROVIDERS:
        return False, f"unknown provider '{provider}'"
    existing = await _get(session, user_id, provider)
    key = api_key or (
        decrypt(existing.api_key_encrypted) if existing and existing.api_key_encrypted else None
    )
    if not key:
        return False, "An API key is required."
    model = (
        default_model
        or (existing.default_model if existing else None)
        or PROVIDERS[provider].default_model
    )
    ok, error = await validate_provider_key(provider, model, key)
    if not ok:
        return False, error
    await upsert_provider_setting(
        session,
        user_id,
        provider,
        api_key=api_key or None,
        default_model=default_model,
        reasoning=reasoning,
        chairman_model=chairman_model,
        chairman_reasoning=chairman_reasoning,
        is_enabled=True,
    )
    return True, None


async def fetch_provider_models(
    session: AsyncSession,
    user_id: str,
    provider: str,
    api_key: str | None = None,
) -> list[ModelInfo]:
    """Fetch the live model catalog for a provider, resolving the key (passed or stored).

    Doubles as the "test the key" step: an invalid key surfaces as a CatalogError from
    `fetch_models`. Read-only — does not persist anything.
    """
    if provider not in PROVIDERS:
        raise ProviderError(f"unknown provider '{provider}'")
    existing = await _get(session, user_id, provider)
    key = api_key or (
        decrypt(existing.api_key_encrypted) if existing and existing.api_key_encrypted else None
    )
    return await fetch_models(provider, key or "")


async def disable_provider(session: AsyncSession, user_id: str, provider: str) -> bool:
    """Disable a provider, keeping its stored key. Flushes; caller commits."""
    existing = await _get(session, user_id, provider)
    if existing is None:
        return False
    existing.is_enabled = False
    await session.flush()
    return True


async def build_configured_providers(session: AsyncSession, user_id: str) -> dict[str, dict]:
    """provider -> {api_key (decrypted), default_model, reasoning, chairman_model,
    chairman_reasoning, enabled} for the resolver."""
    out: dict[str, dict] = {}
    for row in await list_provider_settings(session, user_id):
        out[row.provider] = {
            "api_key": decrypt(row.api_key_encrypted) if row.api_key_encrypted else None,
            "default_model": row.default_model,
            "reasoning": row.reasoning,
            "chairman_model": row.chairman_model,
            "chairman_reasoning": row.chairman_reasoning,
            "enabled": row.is_enabled,
        }
    return out
