"""Fetch a provider's live model catalog using its own SDK's list endpoint.

Catalogs are *live only*: if the provider's API doesn't return a model, the user doesn't have
access to it (there is no curated fallback). Listing also doubles as key validation — an auth
failure surfaces as a `CatalogError`. SDKs are imported lazily so a missing optional provider only
fails when actually selected.
"""

from __future__ import annotations

import asyncio
from typing import TypedDict

from quorum_core.agents.provider import PROVIDERS, ProviderError
from quorum_core.core.config import get_settings


class ModelInfo(TypedDict):
    id: str
    label: str
    supports_reasoning: bool


class CatalogError(RuntimeError):
    """Raised when a provider model listing fails (auth, network, or unsupported)."""


def _short(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return msg.splitlines()[0][:300] if msg else exc.__class__.__name__


def _tag(provider: str, ids_labels: list[tuple[str, str]]) -> list[ModelInfo]:
    """Attach `supports_reasoning` via the provider's ReasoningSpec model pattern, sorted by id."""
    spec = PROVIDERS[provider]
    out: list[ModelInfo] = [
        {
            "id": mid,
            "label": label or mid,
            "supports_reasoning": spec.reasoning.supports_model(mid),
        }
        for mid, label in ids_labels
    ]
    out.sort(key=lambda m: m["id"])
    return out


def _stub_catalog(provider: str) -> list[ModelInfo]:
    """Offline catalog used in test-model mode: the spec's curated suggestions."""
    spec = PROVIDERS[provider]
    return _tag(provider, [(m, m) for m in spec.suggested_models])


async def fetch_models(provider: str, api_key: str) -> list[ModelInfo]:
    """Return the live model catalog for `provider` using `api_key`.

    Raises `ProviderError` for an unknown provider / missing SDK and `CatalogError` for an auth or
    network failure (which the UI treats as "invalid key"). In test-model mode returns a stub.
    """
    p = (provider or "").lower()
    if p not in PROVIDERS:
        raise ProviderError(f"unknown provider '{provider}'; known: {sorted(PROVIDERS)}")
    if not api_key:
        raise CatalogError("An API key is required.")
    if get_settings().use_test_model:
        return _stub_catalog(p)

    try:
        return await asyncio.wait_for(_fetch(p, api_key), timeout=30)
    except (ProviderError, CatalogError):
        raise
    except TimeoutError as exc:
        raise CatalogError("model listing timed out") from exc
    except Exception as exc:  # noqa: BLE001 - surface any provider/auth error to the user
        raise CatalogError(_short(exc)) from exc


async def _fetch(p: str, api_key: str) -> list[ModelInfo]:
    try:
        if p == "anthropic":
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
            pairs: list[tuple[str, str]] = []
            async for m in client.models.list():
                pairs.append((m.id, getattr(m, "display_name", "") or m.id))
            return _tag(p, pairs)

        if p == "openai":
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
            page = await client.models.list()
            # OpenAI lists fine-tunes/embeddings/tts too; keep chat-capable gpt/o-series families.
            pairs = [
                (m.id, m.id)
                for m in page.data
                if m.id.startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))
            ]
            return _tag(p, pairs)

        if p == "google":
            from google import genai

            client = genai.Client(api_key=api_key)
            pairs = []
            async for m in await client.aio.models.list():
                actions = getattr(m, "supported_actions", None) or []
                if actions and "generateContent" not in actions:
                    continue
                mid = (m.name or "").removeprefix("models/")
                if not mid:
                    continue
                pairs.append((mid, getattr(m, "display_name", "") or mid))
            return _tag(p, pairs)

        if p == "groq":
            from groq import AsyncGroq

            client = AsyncGroq(api_key=api_key)
            page = await client.models.list()
            pairs = [(m.id, m.id) for m in page.data]
            return _tag(p, pairs)

        if p == "mistral":
            from mistralai.client import Mistral

            client = Mistral(api_key=api_key)
            resp = await client.models.list_async()
            pairs = [(m.id, getattr(m, "name", "") or m.id) for m in (resp.data or [])]
            return _tag(p, pairs)

        if p == "cohere":
            from cohere import AsyncClientV2

            client = AsyncClientV2(api_key=api_key)
            resp = await client.models.list()
            pairs = [
                (m.name, m.name)
                for m in (resp.models or [])
                if "chat" in (getattr(m, "endpoints", None) or [])
            ]
            return _tag(p, pairs)
    except ImportError as exc:  # pragma: no cover - depends on optional SDKs
        raise ProviderError(f"provider '{p}' SDK is not installed: {exc}") from exc

    raise ProviderError(f"provider '{p}' has no catalog fetcher")  # pragma: no cover
