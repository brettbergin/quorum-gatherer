"""Provider settings API + encryption-at-rest (validation is a no-op in test-model mode)."""

import pytest


@pytest.mark.asyncio
async def test_lists_providers_and_agents(client):
    agents = (await client.get("/api/agents")).json()
    assert len(agents) == 9
    assert any(a["role"] == "chairman" for a in agents)

    settings = (await client.get("/api/settings/providers")).json()
    assert {p["key"] for p in settings["providers"]} >= {"anthropic", "openai", "google"}


@pytest.mark.asyncio
async def test_apply_validates_enables_and_encrypts(client):
    r = await client.post(
        "/api/settings/providers/apply",
        json={"provider": "openai", "api_key": "sk-secret-xyz", "default_model": "gpt-4o-mini"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["has_key"] is True
    assert body["is_enabled"] is True
    assert body["default_model"] == "gpt-4o-mini"

    # The stored key must be ciphertext, and must decrypt back to the original.
    from quorum_core.core.db import SessionLocal
    from quorum_core.core.security import decrypt
    from quorum_core.models import ProviderSetting
    from sqlalchemy import select

    async with SessionLocal() as s:
        row = await s.scalar(select(ProviderSetting).where(ProviderSetting.provider == "openai"))
    assert row.api_key_encrypted != "sk-secret-xyz"
    assert decrypt(row.api_key_encrypted) == "sk-secret-xyz"


@pytest.mark.asyncio
async def test_apply_without_key_is_rejected(client):
    r = await client.post("/api/settings/providers/apply", json={"provider": "google"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_disable_keeps_key_but_turns_off(client):
    await client.post(
        "/api/settings/providers/apply",
        json={"provider": "anthropic", "api_key": "sk-abc"},
    )
    r = await client.post("/api/settings/providers/disable", json={"provider": "anthropic"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_enabled"] is False
    assert body["has_key"] is True  # key retained


@pytest.mark.asyncio
async def test_unknown_provider_rejected(client):
    r = await client.post(
        "/api/settings/providers/apply", json={"provider": "nope", "api_key": "x"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_provider_spec_includes_reasoning_descriptor(client):
    settings = (await client.get("/api/settings/providers")).json()
    by_key = {p["key"]: p for p in settings["providers"]}
    assert by_key["openai"]["reasoning"]["kind"] == "effort"
    assert "high" in by_key["openai"]["reasoning"]["efforts"]
    assert by_key["anthropic"]["reasoning"]["kind"] == "thinking_budget"
    assert by_key["mistral"]["reasoning"]["kind"] == "none"


@pytest.mark.asyncio
async def test_fetch_models_returns_catalog(client):
    # In test-model mode this returns the curated stub catalog, with reasoning flags tagged.
    r = await client.post(
        "/api/settings/providers/models",
        json={"provider": "openai", "api_key": "sk-test"},
    )
    assert r.status_code == 200
    models = r.json()["models"]
    by_id = {m["id"]: m for m in models}
    assert "gpt-4o" in by_id
    assert by_id["o3-mini"]["supports_reasoning"] is True
    assert by_id["gpt-4o"]["supports_reasoning"] is False


@pytest.mark.asyncio
async def test_apply_persists_per_role_models_and_reasoning(client):
    r = await client.post(
        "/api/settings/providers/apply",
        json={
            "provider": "anthropic",
            "api_key": "sk-abc",
            "default_model": "claude-sonnet-4-6",
            "reasoning": "2000",
            "chairman_model": "claude-opus-4-8",
            "chairman_reasoning": "12000",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["default_model"] == "claude-sonnet-4-6"
    assert body["reasoning"] == "2000"
    assert body["chairman_model"] == "claude-opus-4-8"
    assert body["chairman_reasoning"] == "12000"

    settings = (await client.get("/api/settings/providers")).json()
    row = next(s for s in settings["settings"] if s["provider"] == "anthropic")
    assert row["chairman_model"] == "claude-opus-4-8"
    assert row["chairman_reasoning"] == "12000"
