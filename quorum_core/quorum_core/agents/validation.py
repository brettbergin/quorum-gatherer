"""Validate a provider API key by making a tiny real call through pydantic-ai."""

from __future__ import annotations

import asyncio

from pydantic_ai import Agent

from quorum_core.agents.provider import build_model
from quorum_core.core.config import get_settings


def _short(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return msg.splitlines()[0][:300] if msg else exc.__class__.__name__


async def validate_provider_key(provider: str, model: str, api_key: str) -> tuple[bool, str | None]:
    """Return (ok, error). In test-model mode validation is a no-op success."""
    if get_settings().use_test_model:
        return True, None
    try:
        chat_model = build_model(provider, model, api_key)
        agent = Agent(chat_model, model_settings={"max_tokens": 16})
        await asyncio.wait_for(agent.run("Reply with the single word: ok"), timeout=30)
        return True, None
    except TimeoutError:
        return False, "validation request timed out"
    except Exception as exc:  # noqa: BLE001 - surface any provider/auth error to the user
        return False, _short(exc)
