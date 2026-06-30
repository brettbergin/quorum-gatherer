"""DB-backed agents: file→DB ETL, registry parity, edit/reset CRUD, per-session activation."""

import pytest
from quorum_core.agents import orchestrator
from quorum_core.agents.loader import build_registry_from_db, load_agents
from quorum_core.agents.seed import seed_agents
from quorum_core.core.db import SessionLocal
from quorum_core.models import AgentConfig, AgentRun, Chat
from quorum_core.models.enums import AgentRunPhase
from quorum_core.services import agents_service
from quorum_core.services.users import get_or_create_default_user
from sqlalchemy import func, select


async def _seed() -> None:
    async with SessionLocal() as s:
        await seed_agents(s)
        await s.commit()


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_matches_files(client):
    async with SessionLocal() as s:
        n1 = await seed_agents(s)
        await s.commit()
    async with SessionLocal() as s:
        n2 = await seed_agents(s)  # second run inserts nothing
        await s.commit()
        count = await s.scalar(select(func.count()).select_from(AgentConfig))
        reg_db = await build_registry_from_db(s)
    reg_file = load_agents()
    assert n1 == len(reg_file.all()) and n2 == 0
    assert count == len(reg_file.all())
    assert sorted(a.key for a in reg_db.all()) == sorted(a.key for a in reg_file.all())
    assert reg_db.chairman.key == reg_file.chairman.key
    # charter is merged into the DB-backed prompts too
    assert reg_db.members[0].full_system_prompt().strip()


@pytest.mark.asyncio
async def test_update_then_reset_restores_baseline(client):
    await _seed()
    async with SessionLocal() as s:
        before = (await agents_service.get_agent(s, "analyst"))["system_prompt"]
        await agents_service.update_agent(s, "analyst", system_prompt="REPLACED PROMPT")
        await s.commit()
    async with SessionLocal() as s:
        assert (await agents_service.get_agent(s, "analyst"))["system_prompt"] == "REPLACED PROMPT"
        row = await agents_service.reset_agent(s, "analyst")
        await s.commit()
    assert row["system_prompt"] == before  # reverted to the shipped baseline


@pytest.mark.asyncio
async def test_chairman_protected_and_create_member(client):
    await _seed()
    async with SessionLocal() as s:
        with pytest.raises(agents_service.AgentError):
            await agents_service.delete_agent(s, "chairman")
        created = await agents_service.create_agent(
            s, key="devils_advocate", name="Devil's Advocate", system_prompt="Argue the opposite."
        )
        await s.commit()
    assert created["role"] == "council_member" and created["can_reset"] is False
    async with SessionLocal() as s:
        reg = await build_registry_from_db(s)
    assert any(m.key == "devils_advocate" for m in reg.members)


@pytest.mark.asyncio
async def test_deliberation_honors_active_agents(client):
    await _seed()
    reg = load_agents()
    keep = [reg.members[0].key, reg.members[1].key]
    async with SessionLocal() as s:
        user = await get_or_create_default_user(s)
        chat = Chat(user_id=user.id, title="t", idea="idea", active_agents=keep)
        s.add(chat)
        await s.commit()
        cid = chat.id

    await orchestrator.run_deliberation(cid, reg)

    async with SessionLocal() as s:
        runs = list(
            await s.scalars(
                select(AgentRun).where(
                    AgentRun.chat_id == cid, AgentRun.phase == AgentRunPhase.deliberation
                )
            )
        )
    assert sorted(r.agent_key for r in runs) == sorted(keep)  # only the active members ran
