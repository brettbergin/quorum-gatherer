"""Two-phase council: deliberation pauses, per-agent chat, then manual synthesis.

Drives the orchestrator directly (test-model mode) — no API/UI involved.
"""

import pytest
from quorum_core.agents import orchestrator
from quorum_core.agents.loader import load_agents
from quorum_core.core.db import SessionLocal
from quorum_core.models import AgentRun, CouncilReport, Message
from quorum_core.models.enums import (
    AgentRunPhase,
    ChatStatus,
    MessageAuthorType,
)
from quorum_core.services.users import get_or_create_default_user
from sqlalchemy import func, select


async def _new_chat(idea: str = "Launch a doorbell marketing play") -> str:
    async with SessionLocal() as s:
        from quorum_core.models import Chat

        user = await get_or_create_default_user(s)
        chat = Chat(user_id=user.id, title="t", idea=idea)
        s.add(chat)
        await s.commit()
        return chat.id


@pytest.mark.asyncio
async def test_deliberation_pauses_without_report(client):
    reg = load_agents()
    cid = await _new_chat()
    await orchestrator.run_deliberation(cid, reg)

    async with SessionLocal() as s:
        from quorum_core.models import Chat

        chat = await s.get(Chat, cid)
        runs = list(await s.scalars(select(AgentRun).where(AgentRun.chat_id == cid)))
        report = await s.scalar(select(CouncilReport).where(CouncilReport.chat_id == cid))

    assert chat.status == ChatStatus.deliberated
    assert len(runs) == len(reg.members)  # members only — Chairman has NOT run
    assert all(r.phase == AgentRunPhase.deliberation for r in runs)
    assert all(r.message_history for r in runs)  # conversation seeded for each member
    assert report is None  # no synthesis yet


@pytest.mark.asyncio
async def test_chat_appends_turns_and_grows_history(client):
    reg = load_agents()
    cid = await _new_chat()
    await orchestrator.run_deliberation(cid, reg)
    key = reg.members[0].key

    async with SessionLocal() as s:
        run = await s.scalar(
            select(AgentRun).where(AgentRun.chat_id == cid, AgentRun.agent_key == key)
        )
        history_before = run.message_history

    deltas: list[str] = []

    async def on_delta(d: str) -> None:
        deltas.append(d)

    reply = await orchestrator.chat_with_agent(cid, key, "We target SMB installers.", on_delta, reg)
    assert reply  # got a reply
    assert deltas  # it streamed

    async with SessionLocal() as s:
        run = await s.scalar(
            select(AgentRun).where(AgentRun.chat_id == cid, AgentRun.agent_key == key)
        )
        user_msgs = await s.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.chat_id == cid,
                Message.author_key == key,
                Message.author_type == MessageAuthorType.user,
            )
        )
    assert user_msgs == 1
    assert run.message_history and run.message_history != history_before  # grew


@pytest.mark.asyncio
async def test_synthesis_summarizes_only_chatted_agents(client, monkeypatch):
    reg = load_agents()
    cid = await _new_chat()
    await orchestrator.run_deliberation(cid, reg)
    chatted_key = reg.members[0].key
    await orchestrator.chat_with_agent(cid, chatted_key, "Clarification.", None, reg)

    # Spy on the final-position summary so we can assert it's only invoked for chatted agents.
    summarized: list[str] = []
    original = orchestrator._final_position

    async def spy(defn, configured, history_json):
        summarized.append(defn.key)
        return await original(defn, configured, history_json)

    monkeypatch.setattr(orchestrator, "_final_position", spy)

    await orchestrator.run_synthesis(cid, reg)

    assert summarized == [chatted_key]  # only the chatted agent was asked to summarize

    async with SessionLocal() as s:
        from quorum_core.models import Chat

        chat = await s.get(Chat, cid)
        report = await s.scalar(select(CouncilReport).where(CouncilReport.chat_id == cid))
        synth_runs = list(
            await s.scalars(
                select(AgentRun).where(
                    AgentRun.chat_id == cid, AgentRun.phase == AgentRunPhase.synthesis
                )
            )
        )
    assert chat.status == ChatStatus.completed
    assert report is not None
    assert len(synth_runs) == 1  # one Chairman run (re-synthesis replaces, doesn't pile up)
