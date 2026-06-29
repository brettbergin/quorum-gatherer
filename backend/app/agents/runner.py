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
from pydantic_ai.models import Model

from app.agents.definition import AgentDefinition

OnDelta = Callable[[str], Awaitable[None]]


@dataclass
class RunResult:
    text: str
    output: Any
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int


def _build_agent(defn: AgentDefinition, model: Model, output_type: Any) -> Agent:
    return Agent(
        model,
        output_type=output_type,
        instructions=defn.full_system_prompt(),
        model_settings={"temperature": defn.temperature},
        name=defn.key,
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
) -> RunResult:
    agent = _build_agent(defn, model, str)
    start = time.monotonic()
    chunks: list[str] = []
    prompt_tokens = completion_tokens = None
    async with agent.run_stream(prompt) as result:
        async for delta in result.stream_text(delta=True):
            chunks.append(delta)
            if on_delta is not None:
                await on_delta(delta)
        prompt_tokens, completion_tokens = _extract_usage(result)
    text = "".join(chunks)
    return RunResult(
        text=text,
        output=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=int((time.monotonic() - start) * 1000),
    )


async def run_structured(
    defn: AgentDefinition,
    model: Model,
    prompt: str,
    output_type: type[BaseModel],
) -> RunResult:
    agent = _build_agent(defn, model, output_type)
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
