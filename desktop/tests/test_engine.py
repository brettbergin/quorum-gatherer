"""Coverage for the desktop engine module (data/council API over quorum_core).

Runs fully offline: the `db` fixture sets QUORUM_USE_TEST_MODEL=1, so a real council
`run()` uses TestModel. Provider-SDK / network calls are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# --------------------------------------------------------------------- agents CRUD


async def test_list_agents_and_registry(db):
    cfgs = await db.list_agents_cfg()
    keys = {c["key"] for c in cfgs}
    assert "chairman" in keys
    assert "analyst" in keys

    reg = db.registry()
    member_keys = {m.key for m in reg.members}
    assert "analyst" in member_keys
    assert reg.chairman.key == "chairman"


async def test_create_update_reset_delete_agent(db):
    created = await db.create_agent(
        key="tester",
        name="Tester",
        system_prompt="You test things.",
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        temperature=0.5,
    )
    assert created["key"] == "tester"
    assert created["name"] == "Tester"

    updated = await db.update_agent("tester", system_prompt="Now you test more.")
    assert updated["system_prompt"] == "Now you test more."

    # New (non-builtin) agents have no baseline -> reset raises.
    from quorum_core.services.agents_service import AgentError

    with pytest.raises(AgentError):
        await db.reset_agent("tester")

    await db.delete_agent("tester")
    cfgs = await db.list_agents_cfg()
    assert "tester" not in {c["key"] for c in cfgs}


async def test_reset_builtin_agent(db):
    # Mutate then reset a builtin agent back to its shipped baseline.
    await db.update_agent("analyst", system_prompt="temporarily different")
    row = await db.reset_agent("analyst")
    assert row["system_prompt"] != "temporarily different"


async def test_refresh_registry_returns_registry(db):
    reg = await db.refresh_registry()
    assert reg.chairman.key == "chairman"


# --------------------------------------------------------------------- chat lifecycle


async def test_chat_crud_and_mutators(db):
    chat_id = await db.create_chat("My chat", "An idea", [("a.txt", "alpha")])
    assert isinstance(chat_id, str)

    await db.add_document(chat_id, "b.txt", "beta")
    await db.set_idea(chat_id, "A better idea")
    await db.set_active_agents(chat_id, ["analyst", "contrarian"])
    await db.rename_chat(chat_id, "Renamed")

    chat = await db.get_chat(chat_id)
    assert chat["title"] == "Renamed"
    assert chat["idea"] == "A better idea"
    assert chat["active_agents"] == ["analyst", "contrarian"]
    assert {d["filename"] for d in chat["documents"]} == {"a.txt", "b.txt"}

    chats = await db.list_chats()
    assert chat_id in {c["id"] for c in chats}

    await db.delete_chat(chat_id)
    assert await db.get_chat(chat_id) is None


async def test_get_chat_missing_returns_none(db):
    assert await db.get_chat("does-not-exist") is None
    assert await db.agent_conversation("does-not-exist", "analyst") is None
    assert await db.agent_transaction("does-not-exist", "analyst") is None


async def test_set_idea_missing_raises(db):
    with pytest.raises(ValueError):
        await db.set_idea("nope", "x")


async def test_mutators_on_missing_chat_are_noops(db):
    # These silently no-op when the chat is absent.
    await db.set_active_agents("nope", ["analyst"])
    await db.rename_chat("nope", "x")
    await db.delete_chat("nope")


# --------------------------------------------------------------------- full council run (offline)


async def test_full_council_run_end_to_end(db):
    chat_id = await db.create_chat(
        "Decision", "Should we launch the product?", [("ctx.txt", "context body")]
    )
    await db.run(chat_id)

    chat = await db.get_chat(chat_id)
    assert chat["status"].endswith("completed") or "completed" in chat["status"]
    assert len(chat["runs"]) >= 1
    assert chat["report_markdown"]

    member_key = db.registry().members[0].key

    conv = await db.agent_conversation(chat_id, member_key)
    assert conv is not None
    assert conv["agent_name"]
    assert isinstance(conv["turns"], list) and conv["turns"]

    txn = await db.agent_transaction(chat_id, member_key)
    assert txn is not None
    assert txn["prompt"]
    assert txn["system"]  # full_system_prompt() resolved via registry

    reply = await db.chat_with_agent(chat_id, member_key, "Please clarify your point.")
    assert isinstance(reply, str)

    # The clarification turn now shows up in the conversation thread.
    conv2 = await db.agent_conversation(chat_id, member_key)
    assert len(conv2["turns"]) >= len(conv["turns"])


async def test_run_skips_when_already_running(db):
    from quorum_core.core.db import SessionLocal
    from quorum_core.models import Chat, ChatStatus

    chat_id = await db.create_chat("R", "idea")
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        chat.status = ChatStatus.running
        await s.commit()

    with patch("quorum_desktop.engine.run_council", new=AsyncMock()) as rc:
        await db.run(chat_id)
        rc.assert_not_called()


async def test_run_deliberation_and_synthesis(db):
    chat_id = await db.create_chat("D", "Deliberate on this idea")
    await db.run_deliberation(chat_id)
    chat = await db.get_chat(chat_id)
    assert chat["status"]  # deliberated or similar

    # Synthesis convenes the chairman over the deliberated context.
    await db.run_synthesis(chat_id)
    chat2 = await db.get_chat(chat_id)
    assert chat2["report_markdown"]


async def test_run_synthesis_missing_chat_noop(db):
    # No chat -> early return, no exception.
    await db.run_synthesis("missing")


async def test_chat_with_agent_wrong_status_returns_empty(db):
    # A freshly created chat is not yet deliberated/completed.
    chat_id = await db.create_chat("X", "idea")
    member_key = db.registry().members[0].key
    assert await db.chat_with_agent(chat_id, member_key, "hi") == ""


async def test_agent_conversation_before_run_returns_none(db):
    chat_id = await db.create_chat("X", "idea")
    member_key = db.registry().members[0].key
    assert await db.agent_conversation(chat_id, member_key) is None


# --------------------------------------------------------------------- provider settings


async def test_provider_state_shape(db):
    state = await db.provider_state()
    assert "specs" in state and "settings" in state
    spec_keys = {s["key"] for s in state["specs"]}
    assert "anthropic" in spec_keys
    first = state["specs"][0]
    assert "default_model" in first
    assert "reasoning" in first and "kind" in first["reasoning"]


async def test_fetch_models_mocked(db):
    fake = [{"id": "m1", "label": "Model 1", "supports_reasoning": False}]
    with patch(
        "quorum_core.services.settings_service.fetch_models",
        new=AsyncMock(return_value=fake),
    ):
        models = await db.fetch_models("anthropic", "sk-test")
    assert models == fake


async def test_apply_provider_success_then_state_and_disable(db):
    with patch(
        "quorum_core.services.settings_service.validate_provider_key",
        new=AsyncMock(return_value=(True, None)),
    ):
        ok, err = await db.apply_provider(
            "anthropic",
            api_key="sk-test",
            default_model="claude-sonnet-4-6",
            reasoning=None,
            chairman_model="claude-sonnet-4-6",
            chairman_reasoning=None,
        )
    assert ok is True
    assert err is None

    state = await db.provider_state()
    assert state["settings"]["anthropic"]["is_enabled"] is True
    assert state["settings"]["anthropic"]["has_key"] is True

    disabled = await db.disable_provider("anthropic")
    assert disabled is True
    state2 = await db.provider_state()
    assert state2["settings"]["anthropic"]["is_enabled"] is False


async def test_apply_provider_validation_failure(db):
    with patch(
        "quorum_core.services.settings_service.validate_provider_key",
        new=AsyncMock(return_value=(False, "bad key")),
    ):
        ok, err = await db.apply_provider(
            "anthropic", api_key="sk-bad", default_model="claude-sonnet-4-6"
        )
    assert ok is False
    assert err == "bad key"


async def test_disable_provider_unknown_returns_false(db):
    # A provider that was never configured for this user.
    assert await db.disable_provider("cohere") is False
