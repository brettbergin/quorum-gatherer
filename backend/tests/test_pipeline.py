"""End-to-end council pipeline via the API, plus context-isolation assertions."""

import asyncio

import pytest

REPORT_SECTIONS = ["## Executive Summary", "## Final Recommendation", "## Stress Test Results"]


async def _run_council(client, idea="Launch a self-serve tier for SMBs"):
    chat = (await client.post("/api/chats", json={"title": "t", "idea": idea})).json()
    cid = chat["id"]
    files = {"file": ("persona.md", b"ICP: 10-50 person SaaS teams", "text/markdown")}
    await client.post(f"/api/chats/{cid}/documents", files=files)
    await client.post(f"/api/chats/{cid}/items", json={"idea": idea})
    for _ in range(80):
        await asyncio.sleep(0.1)
        r = await client.get(f"/api/chats/{cid}/result")
        if r.status_code == 200:
            return cid, r.json()
    raise AssertionError("pipeline did not finish in time")


@pytest.mark.asyncio
async def test_full_pipeline_completes_and_persists(client):
    cid, report = await _run_council(client)
    assert all(s in report["markdown"] for s in REPORT_SECTIONS)

    detail = (await client.get(f"/api/chats/{cid}")).json()
    assert detail["status"] == "completed"
    assert len(detail["agent_runs"]) == 9
    assert all(r["status"] == "completed" for r in detail["agent_runs"])
    phases = sorted(r["phase"] for r in detail["agent_runs"])
    assert phases.count("deliberation") == 8 and phases.count("synthesis") == 1
    assert detail["report"] is not None


@pytest.mark.asyncio
async def test_reconvening_is_idempotent(client):
    """Re-running the council on a chat that already has a report regenerates cleanly instead
    of hitting the council_reports UNIQUE constraint or piling up duplicate runs."""
    from quorum_core.agents.orchestrator import run_council
    from quorum_core.core.db import SessionLocal
    from quorum_core.models import AgentRun, CouncilReport
    from sqlalchemy import select

    cid, _ = await _run_council(client)

    # A direct second run must not raise (previously: IntegrityError on council_reports.chat_id).
    await run_council(cid)

    async with SessionLocal() as s:
        reports = list(await s.scalars(select(CouncilReport).where(CouncilReport.chat_id == cid)))
        runs = list(await s.scalars(select(AgentRun).where(AgentRun.chat_id == cid)))
    assert len(reports) == 1  # not duplicated
    assert len(runs) == 9  # prior runs cleared, exactly one fresh set

    detail = (await client.get(f"/api/chats/{cid}")).json()
    assert detail["status"] == "completed"


@pytest.mark.asyncio
async def test_members_run_in_isolation(client):
    """Every council member receives the identical prompt (only idea + docs) and none
    sees another member's contribution — proving no cross-agent context leak."""
    cid, _ = await _run_council(client)

    from quorum_core.core.db import SessionLocal
    from quorum_core.models import AgentRun
    from sqlalchemy import select

    async with SessionLocal() as s:
        runs = list(
            await s.scalars(
                select(AgentRun).where(AgentRun.chat_id == cid, AgentRun.phase == "deliberation")
            )
        )

    assert len(runs) == 8
    prompts = {r.input_text for r in runs}
    assert len(prompts) == 1, "all members must receive the same isolated prompt"
    prompt = prompts.pop()
    # The chairman-only synthesis block must never appear in a member's prompt.
    assert "Council deliberations" not in prompt
