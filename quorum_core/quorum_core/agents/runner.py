"""Run a single agent in its own isolated pydantic-ai Agent (no cross-agent context).

Two modes:
- `run_streamed`  — free-text output streamed token-by-token (council members, Phase A).
- `run_structured` — a validated pydantic output object (the Chairman, Phase B).

Each call constructs a fresh `Agent` with only this definition's instructions and a fresh
message history, which is what guarantees context isolation between agents.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.models import Model

from quorum_core.agents.definition import AgentDefinition

OnDelta = Callable[[str], Awaitable[None]]


@dataclass
class RunResult:
    text: str
    output: Any
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    messages: list[ModelMessage] | None = None  # full conversation after the run (for multi-turn)


def serialize_messages(messages: list[ModelMessage]) -> str:
    """pydantic-ai conversation -> JSON string for persistence."""
    return ModelMessagesTypeAdapter.dump_json(messages).decode()


def deserialize_messages(data: str | None) -> list[ModelMessage]:
    """JSON string -> pydantic-ai conversation (empty list if nothing stored)."""
    if not data:
        return []
    return ModelMessagesTypeAdapter.validate_json(data)


def _build_agent(
    defn: AgentDefinition,
    model: Model,
    output_type: Any,
    extra_settings: dict | None = None,
) -> Agent:
    # Allow a few retries: structured synthesis (the Chairman) can occasionally emit output that
    # fails schema validation on the first try, especially on smaller models. `retries` is the
    # default budget for both tool and output-validation retries in pydantic-ai.
    return Agent(
        model,
        output_type=output_type,
        instructions=defn.full_system_prompt(),
        model_settings={"temperature": defn.temperature, **(extra_settings or {})},
        name=defn.key,
        retries=3,
    )


def _extract_usage(result: Any) -> tuple[int | None, int | None]:
    try:
        usage = result.usage()
    except Exception:  # pragma: no cover - usage is best-effort
        return None, None
    prompt = getattr(usage, "input_tokens", None)
    if prompt is None:
        prompt = getattr(usage, "request_tokens", None)
    completion = getattr(usage, "output_tokens", None)
    if completion is None:
        completion = getattr(usage, "response_tokens", None)
    return prompt, completion


async def run_streamed(
    defn: AgentDefinition,
    model: Model,
    prompt: str,
    on_delta: OnDelta | None = None,
    model_settings: dict | None = None,
    message_history: list[ModelMessage] | None = None,
) -> RunResult:
    agent = _build_agent(defn, model, str, model_settings)
    start = time.monotonic()
    chunks: list[str] = []
    prompt_tokens = completion_tokens = None
    messages: list[ModelMessage] | None = None
    async with agent.run_stream(prompt, message_history=message_history or None) as result:
        async for delta in result.stream_text(delta=True):
            chunks.append(delta)
            if on_delta is not None:
                await on_delta(delta)
        prompt_tokens, completion_tokens = _extract_usage(result)
        messages = result.all_messages()
    text = "".join(chunks)
    return RunResult(
        text=text,
        output=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=int((time.monotonic() - start) * 1000),
        messages=messages,
    )


async def run_structured(
    defn: AgentDefinition,
    model: Model,
    prompt: str,
    output_type: type[BaseModel],
    model_settings: dict | None = None,
) -> RunResult:
    agent = _build_agent(defn, model, output_type, model_settings)
    start = time.monotonic()
    result = await agent.run(prompt)
    prompt_tokens, completion_tokens = _extract_usage(result)
    return RunResult(
        text="",
        output=result.output,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=int((time.monotonic() - start) * 1000),
    )
