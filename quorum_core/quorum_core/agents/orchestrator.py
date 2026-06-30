"""The council pipeline: Phase A (concurrent member deliberation) -> Phase B (Chairman
synthesis). Emits events to the bus for live streaming and persists every run.

Runs as a background task. Each concurrent member uses its own DB session (AsyncSession is
not concurrency-safe) and its own freshly-built pydantic-ai Agent (context isolation).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, func, select

from quorum_core.agents import runner
from quorum_core.agents.definition import AgentDefinition
from quorum_core.agents.loader import AgentRegistry, load_agents
from quorum_core.agents.provider import RuntimeModel, build_model, resolve_runtime_model
from quorum_core.agents.synthesis import (
    FINAL_POSITION_PROMPT,
    build_chairman_prompt,
    build_member_prompt,
    render_report_markdown,
)
from quorum_core.core.config import get_settings
from quorum_core.core.db import SessionLocal
from quorum_core.core.events import event_bus
from quorum_core.models import (
    AgentRun,
    AgentRunPhase,
    AgentRunStatus,
    Chat,
    ChatStatus,
    CouncilReport,
    Message,
    MessageAuthorType,
)
from quorum_core.schemas.agent_outputs import CouncilReportContent
from quorum_core.services.settings_service import build_configured_providers


async def _emit(chat_id: str, event: dict) -> None:
    await event_bus.publish(chat_id, event)


async def _reset_chat_artifacts(session, chat_id: str) -> None:
    """Clear a chat's prior run output so re-deliberating is a clean, idempotent restart.

    Wipes the report, all agent runs (incl. their stored chat histories), and every message
    (agent contributions, the Chairman report, and any per-agent clarification turns). Re-running
    on a chat that already produced a report would otherwise hit the `council_reports.chat_id`
    UNIQUE constraint and accumulate duplicate runs/messages.
    """
    await session.execute(delete(CouncilReport).where(CouncilReport.chat_id == chat_id))
    await session.execute(delete(AgentRun).where(AgentRun.chat_id == chat_id))
    await session.execute(delete(Message).where(Message.chat_id == chat_id))


async def _reset_synthesis_artifacts(session, chat_id: str, chairman_key: str) -> None:
    """Clear only the prior synthesis output so the Chairman can be re-convened cleanly.

    Keeps deliberation runs, member contributions, and clarification threads intact; the
    CouncilReport itself is upserted by the Chairman, not deleted here.
    """
    await session.execute(
        delete(AgentRun).where(
            AgentRun.chat_id == chat_id, AgentRun.phase == AgentRunPhase.synthesis
        )
    )
    await session.execute(
        delete(Message).where(Message.chat_id == chat_id, Message.author_key == chairman_key)
    )


def _model_for(rt: RuntimeModel):
    """Build the pydantic-ai model for a run, honoring the TestModel dev toggle."""
    if get_settings().use_test_model:
        from pydantic_ai.models.test import TestModel

        return TestModel()
    return build_model(rt.provider, rt.model, rt.api_key)


def _member_by_key(registry: AgentRegistry, agent_key: str) -> AgentDefinition | None:
    return next((m for m in registry.members if m.key == agent_key), None)


async def run_deliberation(chat_id: str, registry: AgentRegistry | None = None) -> None:
    """Phase A: members deliberate concurrently, then pause (awaiting the Chairman).

    Resets prior artifacts, runs every member, persists each one's contribution + conversation
    history, leaves the chat in `deliberated` status, and emits `deliberation_complete`.
    """
    registry = registry or load_agents()
    try:
        async with SessionLocal() as session:
            chat = await session.get(Chat, chat_id)
            if chat is None or not chat.idea:
                return
            idea = chat.idea
            user_id = chat.user_id
            active = chat.active_agents  # None = all members
            documents = [(d.filename, d.text) for d in await chat.awaitable_attrs.documents]
            configured = await build_configured_providers(session, user_id)
            await _reset_chat_artifacts(session, chat_id)
            chat.status = ChatStatus.running
            await session.commit()

        # Per-session activation: run only the selected members (None = all). Chairman is exempt.
        members = [m for m in registry.members if active is None or m.key in active]

        await _emit(chat_id, {"type": "phase_changed", "phase": "deliberation"})
        for member in members:
            await _emit(
                chat_id,
                {"type": "agent_joined", "agent_key": member.key, "name": member.name},
            )

        member_prompt = build_member_prompt(idea, documents)
        await asyncio.gather(
            *(_run_member(chat_id, member, configured, member_prompt) for member in members)
        )

        async with SessionLocal() as session:
            chat = await session.get(Chat, chat_id)
            if chat is None:
                raise ValueError(f"chat {chat_id} not found")
            chat.status = ChatStatus.deliberated
            await session.commit()
        await _emit(chat_id, {"type": "deliberation_complete"})
    except Exception as exc:  # pragma: no cover - top-level safety net
        await _fail_chat(chat_id, exc)


async def run_synthesis(chat_id: str, registry: AgentRegistry | None = None) -> None:
    """Phase B: build each member's latest position (summarizing chatted agents), then synthesize.

    Re-derives contributions from the DB so it can run long after deliberation and reflect any
    clarification chats. Idempotent: re-runnable after further chatting.
    """
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
            await _reset_synthesis_artifacts(session, chat_id, registry.chairman.key)
            chat.status = ChatStatus.running
            await session.commit()

        contributions = await _collect_contributions(chat_id, registry, configured)

        await _emit(chat_id, {"type": "phase_changed", "phase": "synthesis"})
        await _run_chairman(chat_id, registry.chairman, configured, idea, documents, contributions)

        async with SessionLocal() as session:
            chat = await session.get(Chat, chat_id)
            if chat is None:
                raise ValueError(f"chat {chat_id} not found")
            chat.status = ChatStatus.completed
            await session.commit()
    except Exception as exc:  # pragma: no cover - top-level safety net
        await _fail_chat(chat_id, exc)


async def run_council(chat_id: str, registry: AgentRegistry | None = None) -> None:
    """One-shot deliberation + synthesis (no clarification step). Used by the web API and tests."""
    registry = registry or load_agents()
    await run_deliberation(chat_id, registry)
    async with SessionLocal() as session:
        chat = await session.get(Chat, chat_id)
        if chat is None or chat.status != ChatStatus.deliberated:
            return  # deliberation failed; the error was already emitted
    await run_synthesis(chat_id, registry)


async def _fail_chat(chat_id: str, exc: Exception) -> None:
    async with SessionLocal() as session:
        chat = await session.get(Chat, chat_id)
        if chat is not None:
            chat.status = ChatStatus.failed
            await session.commit()
    await _emit(chat_id, {"type": "error", "message": str(exc)})


async def _collect_contributions(
    chat_id: str, registry: AgentRegistry, configured: dict[str, dict]
) -> list[tuple[str, str]]:
    """Latest position per member: a final-position summary for chatted agents, else the
    initial contribution. Ordered by the registry's member order for a stable Chairman prompt."""
    async with SessionLocal() as session:
        runs = list(
            await session.scalars(
                select(AgentRun).where(
                    AgentRun.chat_id == chat_id,
                    AgentRun.phase == AgentRunPhase.deliberation,
                )
            )
        )
        chatted: dict[str, bool] = {}
        for member in registry.members:
            count = await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.chat_id == chat_id,
                    Message.author_key == member.key,
                    Message.author_type == MessageAuthorType.user,
                )
            )
            chatted[member.key] = bool(count)
    runs_by_key = {r.agent_key: r for r in runs}

    contributions: list[tuple[str, str]] = []
    for member in registry.members:
        run = runs_by_key.get(member.key)
        if run is None or not (run.output_text or run.message_history):
            continue
        if chatted.get(member.key) and run.message_history:
            text = await _final_position(member, configured, run.message_history)
        else:
            text = run.output_text or ""
        if text:
            contributions.append((member.name, text))
    return contributions


async def _final_position(
    defn: AgentDefinition, configured: dict[str, dict], history_json: str
) -> str:
    """Ask a chatted agent for its concise, updated position using its full thread as history."""
    rt = resolve_runtime_model(
        default_provider=defn.default_provider,
        default_model=defn.default_model,
        configured=configured,
        is_chairman=False,
    )
    model = _model_for(rt)
    history = runner.deserialize_messages(history_json)
    result = await runner.run_streamed(
        defn,
        model,
        FINAL_POSITION_PROMPT,
        model_settings=rt.model_settings,
        message_history=history,
    )
    return result.text


async def chat_with_agent(
    chat_id: str,
    agent_key: str,
    user_message: str,
    on_delta: runner.OnDelta | None = None,
    registry: AgentRegistry | None = None,
) -> str:
    """One clarification turn with a single member: stream a reply that's aware of the full thread,
    then persist the user+agent messages and the updated conversation history. Returns the reply."""
    registry = registry or load_agents()
    defn = _member_by_key(registry, agent_key)
    if defn is None:
        raise ValueError(f"unknown council member '{agent_key}'")

    async with SessionLocal() as session:
        chat = await session.get(Chat, chat_id)
        if chat is None:
            raise ValueError("chat not found")
        configured = await build_configured_providers(session, chat.user_id)
        run = await session.scalar(
            select(AgentRun).where(
                AgentRun.chat_id == chat_id,
                AgentRun.agent_key == agent_key,
                AgentRun.phase == AgentRunPhase.deliberation,
            )
        )
        history_json = run.message_history if run else None
        run_id = run.id if run else None

    rt = resolve_runtime_model(
        default_provider=defn.default_provider,
        default_model=defn.default_model,
        configured=configured,
        is_chairman=False,
    )
    model = _model_for(rt)
    history = runner.deserialize_messages(history_json)
    result = await runner.run_streamed(
        defn,
        model,
        user_message,
        on_delta,
        model_settings=rt.model_settings,
        message_history=history,
    )

    async with SessionLocal() as session:
        session.add(
            Message(
                chat_id=chat_id,
                author_type=MessageAuthorType.user,
                author_key=agent_key,
                content=user_message,
            )
        )
        session.add(
            Message(
                chat_id=chat_id,
                author_type=MessageAuthorType.agent,
                author_key=agent_key,
                content=result.text,
            )
        )
        if run_id is not None and result.messages is not None:
            run = await session.get(AgentRun, run_id)
            if run is None:
                raise ValueError(f"agent run {run_id} not found")
            run.message_history = runner.serialize_messages(result.messages)
        await session.commit()
    return result.text


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
        is_chairman=False,
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
        result = await runner.run_streamed(
            defn, model, prompt, on_delta, model_settings=rt.model_settings
        )
    except Exception as exc:
        async with SessionLocal() as session:
            run_row = await session.get(AgentRun, run_id)
            if run_row is None:
                raise ValueError(f"agent run {run_id} not found") from exc
            run_row.status = AgentRunStatus.failed
            run_row.error = str(exc)
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
        run_row = await session.get(AgentRun, run_id)
        if run_row is None:
            raise ValueError(f"agent run {run_id} not found")
        run_row.status = AgentRunStatus.completed
        run_row.output_text = result.text
        run_row.prompt_tokens = result.prompt_tokens
        run_row.completion_tokens = result.completion_tokens
        run_row.latency_ms = result.latency_ms
        if result.messages is not None:
            run_row.message_history = runner.serialize_messages(result.messages)
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
        is_chairman=True,
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
        result = await runner.run_structured(
            defn, model, prompt, CouncilReportContent, model_settings=rt.model_settings
        )
        content: CouncilReportContent = result.output
    except Exception as exc:
        async with SessionLocal() as session:
            run_row = await session.get(AgentRun, run_id)
            if run_row is None:
                raise ValueError(f"agent run {run_id} not found") from exc
            run_row.status = AgentRunStatus.failed
            run_row.error = str(exc)
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
        run_row = await session.get(AgentRun, run_id)
        if run_row is None:
            raise ValueError(f"agent run {run_id} not found")
        run_row.status = AgentRunStatus.completed
        run_row.output = payload
        run_row.output_text = markdown
        run_row.prompt_tokens = result.prompt_tokens
        run_row.completion_tokens = result.completion_tokens
        run_row.latency_ms = result.latency_ms
        # Idempotent write: replace any existing report (defends against a re-run/race that
        # slipped past the start-of-run reset) rather than violating the chat_id UNIQUE.
        existing = await session.scalar(
            select(CouncilReport).where(CouncilReport.chat_id == chat_id)
        )
        if existing is not None:
            existing.content = payload
            existing.markdown = markdown
        else:
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
