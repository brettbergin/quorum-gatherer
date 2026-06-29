"""Provider settings API + encryption-at-rest."""

import pytest


@pytest.mark.asyncio
async def test_lists_providers_and_agents(client):
    agents = (await client.get("/api/agents")).json()
    assert len(agents) == 9
    assert any(a["role"] == "chairman" for a in agents)

    settings = (await client.get("/api/settings/providers")).json()
    assert {p["key"] for p in settings["providers"]} >= {"anthropic", "openai", "google"}


@pytest.mark.asyncio
async def test_provider_setting_roundtrip_is_encrypted(client):
    r = await client.put(
        "/api/settings/providers",
        json={"provider": "openai", "api_key": "sk-secret-xyz", "default_model": "gpt-4o-mini"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["has_key"] is True and body["default_model"] == "gpt-4o-mini"

    # The stored key must be ciphertext, and must decrypt back to the original.
    from app.core.db import SessionLocal
    from app.core.security import decrypt
    from app.models import ProviderSetting
    from sqlalchemy import select

    async with SessionLocal() as s:
        row = await s.scalar(select(ProviderSetting).where(ProviderSetting.provider == "openai"))
    assert row.api_key_encrypted != "sk-secret-xyz"
    assert decrypt(row.api_key_encrypted) == "sk-secret-xyz"


@pytest.mark.asyncio
async def test_unknown_provider_rejected(client):
    r = await client.put("/api/settings/providers", json={"provider": "nope", "api_key": "x"})
    assert r.status_code == 400
