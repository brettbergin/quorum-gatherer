"""Per-provider reasoning knobs: build_reasoning_settings + resolver threading + catalog stub."""

import pytest
from quorum_core.agents.catalog import fetch_models
from quorum_core.agents.provider import (
    PROVIDERS,
    build_reasoning_settings,
    resolve_runtime_model,
)


def test_openai_effort_maps_to_settings():
    assert build_reasoning_settings("openai", "o3-mini", "high") == {
        "openai_reasoning_effort": "high"
    }


def test_openai_effort_ignored_for_non_reasoning_model():
    # gpt-4o is not a reasoning model -> no knob emitted.
    assert build_reasoning_settings("openai", "gpt-4o", "high") == {}


def test_openai_invalid_effort_dropped():
    assert build_reasoning_settings("openai", "o3-mini", "bogus") == {}


def test_anthropic_thinking_budget_shape_and_clamp():
    spec = PROVIDERS["anthropic"].reasoning
    out = build_reasoning_settings("anthropic", "claude-opus-4-8", str(spec.budget_max + 999))
    assert out == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": spec.budget_max}
    }


def test_google_thinking_config_shape():
    out = build_reasoning_settings("google", "gemini-2.5-pro", "4096")
    assert out == {"google_thinking_config": {"thinking_budget": 4096, "include_thoughts": False}}


def test_providers_without_reasoning_emit_nothing():
    assert build_reasoning_settings("mistral", "mistral-large-latest", "high") == {}
    assert build_reasoning_settings("cohere", "command-r-plus", "8000") == {}


def test_blank_or_disabled_reasoning_is_empty():
    assert build_reasoning_settings("anthropic", "claude-opus-4-8", None) == {}
    assert build_reasoning_settings("anthropic", "claude-opus-4-8", "0") == {}


def test_resolver_threads_reasoning_into_model_settings():
    configured = {
        "anthropic": {
            "api_key": "sk-test",
            "default_model": "claude-opus-4-8",
            "reasoning": "8000",
            "enabled": True,
        }
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        configured=configured,
    )
    assert rt.provider == "anthropic"
    assert rt.model == "claude-opus-4-8"
    assert rt.model_settings == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": 8000}
    }


def test_chairman_not_downgraded_to_member_model():
    # Member model configured to sonnet; chairman model left unset -> chairman keeps its own
    # default (opus), never the member's sonnet. This is the regression we fixed.
    configured = {
        "anthropic": {
            "api_key": "sk-test",
            "default_model": "claude-sonnet-4-6",
            "enabled": True,
        }
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-opus-4-8",  # the chairman agent's own default
        configured=configured,
        is_chairman=True,
    )
    assert rt.model == "claude-opus-4-8"


def test_chairman_uses_its_own_configured_model_and_reasoning():
    configured = {
        "anthropic": {
            "api_key": "sk-test",
            "default_model": "claude-sonnet-4-6",
            "reasoning": "2000",
            "chairman_model": "claude-opus-4-8",
            "chairman_reasoning": "12000",
            "enabled": True,
        }
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-opus-4-8",
        configured=configured,
        is_chairman=True,
    )
    assert rt.model == "claude-opus-4-8"
    assert rt.model_settings == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": 12000}
    }


def test_member_uses_configured_member_model():
    configured = {
        "anthropic": {
            "api_key": "sk-test",
            "default_model": "claude-haiku-4-5",
            "chairman_model": "claude-opus-4-8",
            "enabled": True,
        }
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        configured=configured,
        is_chairman=False,
    )
    assert rt.model == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_catalog_stub_in_test_model_mode(monkeypatch):
    # In test-model mode fetch_models returns the curated stub (no network).
    from types import SimpleNamespace

    import quorum_core.agents.catalog as catalog_mod

    monkeypatch.setattr(
        catalog_mod, "get_settings", lambda: SimpleNamespace(use_test_model=True)
    )
    models = await fetch_models("openai", "sk-anything")
    ids = {m["id"] for m in models}
    assert "gpt-4o" in ids
    # o3-mini is a reasoning model; gpt-4o is not.
    by_id = {m["id"]: m for m in models}
    assert by_id["o3-mini"]["supports_reasoning"] is True
    assert by_id["gpt-4o"]["supports_reasoning"] is False
