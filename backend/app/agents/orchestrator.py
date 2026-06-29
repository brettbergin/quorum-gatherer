"""The council pipeline: Phase A (concurrent member deliberation) -> Phase B (Chairman
synthesis). Emits events to the bus for live streaming and persists every run.

Runs as a background task. Each concurrent member uses its own DB session (AsyncSession is
not concurrency-safe) and its own freshly-built pydantic-ai Agent (context isolation).
"""

from __future__ import annotations

import asyncio

from app.agents import runner
from app.agents.definition import AgentDefinition
from app.agents.loader import AgentRegistry, load_agents
from app.agents.provider import RuntimeModel, build_model, resolve_runtime_model
from app.agents.synthesis import (
    build_chairman_prompt,
    build_member_prompt,
    render_report_markdown,
)
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.events import event_bus
from app.models import (
    AgentRun,
    AgentRunPhase,
    AgentRunStatus,
    Chat,
    ChatStatus,
    CouncilReport,
    Message,
    MessageAuthorType,
)
from app.schemas.agent_outputs import CouncilReportContent
from app.services.settings_service import build_configured_providers


async def _emit(chat_id: str, event: dict) -> None:
    await event_bus.publish(chat_id, event)


def _model_for(rt: RuntimeModel):
    """Build the pydantic-ai model for a run, honoring the TestModel dev toggle."""
    if get_settings().use_test_model:
        from pydantic_ai.models.test import TestModel

        return TestModel()
    return build_model(rt.provider, rt.model, rt.api_key)


async def run_council(chat_id: str, registry: AgentRegistry | None = None) -> None:
    registry = registry or load_agents()
    try:
        async with SessionLocal() as session:
            chat = await session.get(Chat, chat_id)
            if chat is None or not chat.idea:
                return
            idea = chat.idea
            user_id = chat.user_id
            documents = [(d.filename, d.text) for d in await chat.awaitable_attrs.documents]
            configured = await build_configured_providers(session, user_id)
            chat.status = ChatStatus.running
            await session.commit()

        await _emit(chat_id, {"type": "phase_changed", "phase": "deliberation"})
        for member in registry.members:
            await _emit(
                chat_id,
                {"type": "agent_joined", "agent_key": member.key, "name": member.name},
            )

        member_prompt = build_member_prompt(idea, documents)
        results = await asyncio.gather(
            *(
                _run_member(chat_id, member, configured, member_prompt)
                for member in registry.members
            )
        )
        contributions = [(name, text) for (name, text) in results if text]

        await _emit(chat_id, {"type": "phase_changed", "phase": "synthesis"})
        await _run_chairman(chat_id, registry.chairman, configured, idea, documents, contributions)

        async with SessionLocal() as session:
            chat = await session.get(Chat, chat_id)
            chat.status = ChatStatus.completed
            await session.commit()
    except Exception as exc:  # pragma: no cover - top-level safety net
        async with SessionLocal() as session:
            chat = await session.get(Chat, chat_id)
            if chat is not None:
                chat.status = ChatStatus.failed
                await session.commit()
        await _emit(chat_id, {"type": "error", "message": str(exc)})


async def _run_member(
    chat_id: str,
    defn: AgentDefinition,
    configured: dict[str, dict],
    prompt: str,
) -> tuple[str, str | None]:
    rt = resolve_runtime_model(
        default_provider=defn.default_provider,
        default_model=defn.default_model,
        configured=configured,
    )

    async with SessionLocal() as session:
        run = AgentRun(
            chat_id=chat_id,
            agent_key=defn.key,
            agent_name=defn.name,
            phase=AgentRunPhase.deliberation,
            status=AgentRunStatus.running,
            provider=rt.provider,
            model=rt.model,
            input_text=prompt,
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    await _emit(
        chat_id,
        {
            "type": "agent_run_started",
            "agent_key": defn.key,
            "name": defn.name,
            "run_id": run_id,
            "provider": rt.provider,
            "model": rt.model,
        },
    )

    async def on_delta(delta: str) -> None:
        await _emit(
            chat_id,
            {"type": "agent_token", "agent_key": defn.key, "run_id": run_id, "delta": delta},
        )

    try:
        model = _model_for(rt)
        result = await runner.run_streamed(defn, model, prompt, on_delta)
    except Exception as exc:
        async with SessionLocal() as session:
            run = await session.get(AgentRun, run_id)
            run.status = AgentRunStatus.failed
            run.error = str(exc)
            await session.commit()
        await _emit(
            chat_id,
            {
                "type": "agent_run_failed",
                "agent_key": defn.key,
                "run_id": run_id,
                "error": str(exc),
            },
        )
        return defn.name, None

    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        run.status = AgentRunStatus.completed
        run.output_text = result.text
        run.prompt_tokens = result.prompt_tokens
        run.completion_tokens = result.completion_tokens
        run.latency_ms = result.latency_ms
        session.add(
            Message(
                chat_id=chat_id,
                author_type=MessageAuthorType.agent,
                author_key=defn.key,
                content=result.text,
            )
        )
        await session.commit()

    await _emit(
        chat_id,
        {
            "type": "agent_run_complete",
            "agent_key": defn.key,
            "run_id": run_id,
            "text": result.text,
        },
    )
    return defn.name, result.text


async def _run_chairman(
    chat_id: str,
    defn: AgentDefinition,
    configured: dict[str, dict],
    idea: str,
    documents: list[tuple[str, str]],
    contributions: list[tuple[str, str]],
) -> None:
    rt = resolve_runtime_model(
        default_provider=defn.default_provider,
        default_model=defn.default_model,
        configured=configured,
    )

    async with SessionLocal() as session:
        run = AgentRun(
            chat_id=chat_id,
            agent_key=defn.key,
            agent_name=defn.name,
            phase=AgentRunPhase.synthesis,
            status=AgentRunStatus.running,
            provider=rt.provider,
            model=rt.model,
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    await _emit(
        chat_id,
        {
            "type": "agent_run_started",
            "agent_key": defn.key,
            "name": defn.name,
            "run_id": run_id,
            "provider": rt.provider,
            "model": rt.model,
        },
    )

    prompt = build_chairman_prompt(idea, documents, contributions)
    try:
        model = _model_for(rt)
        result = await runner.run_structured(defn, model, prompt, CouncilReportContent)
        content: CouncilReportContent = result.output
    except Exception as exc:
        async with SessionLocal() as session:
            run = await session.get(AgentRun, run_id)
            run.status = AgentRunStatus.failed
            run.error = str(exc)
            await session.commit()
        await _emit(
            chat_id,
            {
                "type": "agent_run_failed",
                "agent_key": defn.key,
                "run_id": run_id,
                "error": str(exc),
            },
        )
        raise

    markdown = render_report_markdown(content)
    payload = content.model_dump(mode="json")

    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        run.status = AgentRunStatus.completed
        run.output = payload
        run.output_text = markdown
        run.prompt_tokens = result.prompt_tokens
        run.completion_tokens = result.completion_tokens
        run.latency_ms = result.latency_ms
        session.add(CouncilReport(chat_id=chat_id, content=payload, markdown=markdown))
        session.add(
            Message(
                chat_id=chat_id,
                author_type=MessageAuthorType.agent,
                author_key=defn.key,
                content=markdown,
            )
        )
        await session.commit()

    await _emit(
        chat_id,
        {
            "type": "council_report",
            "agent_key": defn.key,
            "run_id": run_id,
            "content": payload,
            "markdown": markdown,
        },
    )
