"""Thin desktop-side data/engine operations over quorum_core (no HTTP layer).

Mirrors what the web API does, but calls the engine + ORM directly against the local DB.
Returns plain dicts so the Qt layer stays decoupled from detached ORM instances.
"""

from __future__ import annotations

from quorum_core.agents.loader import (
    AgentRegistry,
    build_registry_from_db,
    load_agents,
)
from quorum_core.agents.orchestrator import (
    chat_with_agent as svc_chat_with_agent,
)
from quorum_core.agents.orchestrator import (
    run_council,
)
from quorum_core.agents.orchestrator import (
    run_deliberation as svc_run_deliberation,
)
from quorum_core.agents.orchestrator import (
    run_synthesis as svc_run_synthesis,
)
from quorum_core.agents.provider import list_provider_specs
from quorum_core.agents.seed import seed_agents
from quorum_core.core.db import SessionLocal
from quorum_core.models import (
    AgentRun,
    AgentRunPhase,
    Chat,
    ChatDocument,
    ChatStatus,
    Message,
    MessageAuthorType,
)
from quorum_core.services.agents_service import (
    create_agent as svc_create_agent,
)
from quorum_core.services.agents_service import (
    delete_agent as svc_delete_agent,
)
from quorum_core.services.agents_service import (
    list_agents as svc_list_agents,
)
from quorum_core.services.agents_service import (
    reset_agent as svc_reset_agent,
)
from quorum_core.services.agents_service import (
    update_agent as svc_update_agent,
)
from quorum_core.services.settings_service import (
    apply_provider as svc_apply_provider,
)
from quorum_core.services.settings_service import (
    disable_provider as svc_disable_provider,
)
from quorum_core.services.settings_service import (
    fetch_provider_models as svc_fetch_provider_models,
)
from quorum_core.services.settings_service import (
    list_provider_settings,
)
from quorum_core.services.users import get_or_create_default_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

_registry: AgentRegistry | None = None


def registry() -> AgentRegistry:
    """The cached council registry. Falls back to file-based load if not yet built from the DB."""
    global _registry
    if _registry is None:
        _registry = load_agents()
    return _registry


async def ensure_agents() -> None:
    """First-boot ETL of shipped prompts into the DB, then build the registry from the DB.

    Called once at desktop startup. After this the app reads agents from the DB.
    """
    async with SessionLocal() as s:
        await seed_agents(s)
        await s.commit()
    await refresh_registry()


async def refresh_registry() -> AgentRegistry:
    """Rebuild the cached registry from the DB (after an agent edit/add/delete)."""
    global _registry
    async with SessionLocal() as s:
        _registry = await build_registry_from_db(s)
    return _registry


# --------------------------------------------------------------------- agent roster (CRUD)


async def list_agents_cfg() -> list[dict]:
    async with SessionLocal() as s:
        return await svc_list_agents(s)


async def create_agent(key: str, name: str, system_prompt: str, **fields) -> dict:
    async with SessionLocal() as s:
        row = await svc_create_agent(s, key=key, name=name, system_prompt=system_prompt, **fields)
        await s.commit()
    await refresh_registry()
    return row


async def update_agent(key: str, system_prompt: str | None = None, **fields) -> dict:
    async with SessionLocal() as s:
        row = await svc_update_agent(s, key, system_prompt=system_prompt, **fields)
        await s.commit()
    await refresh_registry()
    return row


async def delete_agent(key: str) -> None:
    async with SessionLocal() as s:
        await svc_delete_agent(s, key)
        await s.commit()
    await refresh_registry()


async def reset_agent(key: str) -> dict:
    async with SessionLocal() as s:
        row = await svc_reset_agent(s, key)
        await s.commit()
    await refresh_registry()
    return row


async def create_chat(
    title: str | None, idea: str | None, documents: list[tuple[str, str]] | None = None
) -> str:
    async with SessionLocal() as s:
        user = await get_or_create_default_user(s)
        chat = Chat(user_id=user.id, title=title, idea=idea, status=ChatStatus.created)
        s.add(chat)
        await s.flush()
        for filename, text in documents or []:
            s.add(
                ChatDocument(
                    chat_id=chat.id, filename=filename, content_type="text/plain", text=text
                )
            )
        await s.commit()
        return chat.id


async def add_document(chat_id: str, filename: str, text: str) -> None:
    async with SessionLocal() as s:
        s.add(
            ChatDocument(chat_id=chat_id, filename=filename, content_type="text/plain", text=text)
        )
        await s.commit()


async def set_idea(chat_id: str, idea: str) -> None:
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is None:
            raise ValueError(f"chat not found: {chat_id}")
        chat.idea = idea
        chat.status = ChatStatus.created
        await s.commit()


async def set_active_agents(chat_id: str, keys: list[str]) -> None:
    """Persist which council members participate in this chat's deliberation (per-session)."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is not None:
            chat.active_agents = list(keys)
            await s.commit()


async def rename_chat(chat_id: str, title: str) -> None:
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is not None:
            chat.title = title.strip() or None
            await s.commit()


async def delete_chat(chat_id: str) -> None:
    """Delete a session and all its runs/messages/report/documents (ORM + FK cascade)."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is not None:
            await s.delete(chat)
            await s.commit()


async def run(chat_id: str) -> None:
    """One-shot deliberation + synthesis (legacy; kept for completeness)."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is not None and chat.status == ChatStatus.running:
            return
    await run_council(chat_id, registry())


async def run_deliberation(chat_id: str) -> None:
    """Phase A only: members deliberate and the council pauses (awaiting the Chairman)."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is not None and chat.status == ChatStatus.running:
            return
    await svc_run_deliberation(chat_id, registry())


async def run_synthesis(chat_id: str) -> None:
    """Phase B only: convene the Chairman over the latest per-agent context."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is None or chat.status == ChatStatus.running:
            return  # nothing to synthesize, or a phase is already in flight
    await svc_run_synthesis(chat_id, registry())


async def chat_with_agent(chat_id: str, agent_key: str, message: str, on_delta=None) -> str:
    """Send one clarification message to a member and stream its reply (after deliberation)."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is None or chat.status not in (ChatStatus.deliberated, ChatStatus.completed):
            return ""
    return await svc_chat_with_agent(chat_id, agent_key, message, on_delta, registry())


async def agent_conversation(chat_id: str, agent_key: str) -> dict | None:
    """Display thread for one agent: the opening idea, the agent's contribution, then any
    clarification turns."""
    async with SessionLocal() as s:
        chat = await s.get(Chat, chat_id)
        if chat is None:
            return None
        run = await s.scalar(
            select(AgentRun).where(
                AgentRun.chat_id == chat_id,
                AgentRun.agent_key == agent_key,
                AgentRun.phase == AgentRunPhase.deliberation,
            )
        )
        if run is None:
            return None
        msgs = list(
            await s.scalars(
                select(Message)
                .where(Message.chat_id == chat_id, Message.author_key == agent_key)
                .order_by(Message.created_at, Message.id)
            )
        )
    turns: list[dict] = []
    # Seed with the exact prompt the agent was given (idea + context documents + instruction),
    # so the user can see the full context the agent had before any clarification.
    opening = run.input_text or chat.idea
    if opening:
        turns.append({"role": "user", "content": opening})
    seen_initial = False
    for m in msgs:
        role = "agent" if m.author_type == MessageAuthorType.agent else "user"
        if role == "agent" and not seen_initial:
            seen_initial = True
        turns.append({"role": role, "content": m.content})
    if not seen_initial and run.output_text:
        # No persisted agent message yet — fall back to the run's contribution text.
        insert_at = 1 if opening else 0
        turns.insert(insert_at, {"role": "agent", "content": run.output_text})
    return {
        "agent_name": run.agent_name,
        "provider": run.provider,
        "model": run.model,
        "turns": turns,
    }


async def list_chats() -> list[dict]:
    async with SessionLocal() as s:
        rows = await s.scalars(select(Chat).order_by(Chat.created_at.desc()))
        return [
            {"id": c.id, "title": c.title, "status": str(c.status), "idea": c.idea} for c in rows
        ]


async def get_chat(chat_id: str) -> dict | None:
    async with SessionLocal() as s:
        chat = await s.scalar(
            select(Chat)
            .where(Chat.id == chat_id)
            .options(
                selectinload(Chat.documents),
                selectinload(Chat.agent_runs),
                selectinload(Chat.messages),
                selectinload(Chat.report),
            )
        )
        if chat is None:
            return None
        # Agents the user has sent at least one clarification to (for the "engaged" marker).
        chatted = {
            m.author_key
            for m in chat.messages
            if m.author_type == MessageAuthorType.user and m.author_key
        }
        return {
            "id": chat.id,
            "title": chat.title,
            "idea": chat.idea,
            "status": str(chat.status),
            "active_agents": chat.active_agents,  # None = all members active
            "documents": [{"id": d.id, "filename": d.filename} for d in chat.documents],
            "runs": [
                {
                    "agent_key": r.agent_key,
                    "agent_name": r.agent_name,
                    "phase": str(r.phase),
                    "status": str(r.status),
                    "provider": r.provider,
                    "model": r.model,
                    "output_text": r.output_text,
                    "error": r.error,
                    "chatted": r.agent_key in chatted,
                }
                for r in chat.agent_runs
                if r.phase == AgentRunPhase.deliberation
            ],
            "report_markdown": chat.report.markdown if chat.report else None,
        }


def _definition_by_key(agent_key: str):
    reg = registry()
    for defn in (*reg.members, reg.chairman):
        if defn.key == agent_key:
            return defn
    return None


async def agent_transaction(chat_id: str, agent_key: str) -> dict | None:
    """The full LLM transaction for one agent in a chat: system instructions + prompt + response.

    Returns None if the agent hasn't run yet for this chat.
    """
    async with SessionLocal() as s:
        run = await s.scalar(
            select(AgentRun)
            .where(AgentRun.chat_id == chat_id, AgentRun.agent_key == agent_key)
            .order_by(AgentRun.created_at.desc())
        )
        if run is None:
            return None
        defn = _definition_by_key(agent_key)
        return {
            "agent_name": run.agent_name,
            "provider": run.provider,
            "model": run.model,
            "status": str(run.status),
            "phase": str(run.phase),
            "system": defn.full_system_prompt() if defn else None,
            "prompt": run.input_text,
            "response": run.output_text,
            "error": run.error,
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
            "latency_ms": run.latency_ms,
        }


# --------------------------------------------------------------------- provider settings


async def provider_state() -> dict:
    """All provider specs + the user's current per-provider settings."""
    async with SessionLocal() as s:
        user = await get_or_create_default_user(s)
        await s.commit()
        rows = await list_provider_settings(s, user.id)
    specs = [
        {
            "key": sp.key,
            "label": sp.label,
            "default_model": sp.default_model,
            "suggested": list(sp.suggested_models),
            "reasoning": {
                "kind": sp.reasoning.kind,
                "settings_key": sp.reasoning.settings_key,
                "efforts": list(sp.reasoning.efforts),
                "budget_min": sp.reasoning.budget_min,
                "budget_max": sp.reasoning.budget_max,
                "budget_default": sp.reasoning.budget_default,
                "model_pattern": sp.reasoning.model_pattern,
            },
        }
        for sp in list_provider_specs()
    ]
    settings = {
        r.provider: {
            "has_key": bool(r.api_key_encrypted),
            "default_model": r.default_model,
            "reasoning": r.reasoning,
            "chairman_model": r.chairman_model,
            "chairman_reasoning": r.chairman_reasoning,
            "is_enabled": r.is_enabled,
        }
        for r in rows
    }
    return {"specs": specs, "settings": settings}


async def fetch_models(provider: str, api_key: str | None) -> list[dict]:
    """Fetch a provider's live model catalog (also validates the key).

    Returns a list of {"id", "label", "supports_reasoning"}. Raises CatalogError on an invalid
    key / network failure for the UI to surface.
    """
    async with SessionLocal() as s:
        user = await get_or_create_default_user(s)
        await s.commit()
        models = await svc_fetch_provider_models(s, user.id, provider, api_key=api_key)
    return [dict(m) for m in models]


async def apply_provider(
    provider: str,
    api_key: str | None,
    default_model: str | None,
    reasoning: str | None = None,
    chairman_model: str | None = None,
    chairman_reasoning: str | None = None,
) -> tuple[bool, str | None]:
    async with SessionLocal() as s:
        user = await get_or_create_default_user(s)
        await s.commit()
        ok, error = await svc_apply_provider(
            s,
            user.id,
            provider,
            api_key=api_key,
            default_model=default_model,
            reasoning=reasoning,
            chairman_model=chairman_model,
            chairman_reasoning=chairman_reasoning,
        )
        if ok:
            await s.commit()
        return ok, error


async def disable_provider(provider: str) -> bool:
    async with SessionLocal() as s:
        user = await get_or_create_default_user(s)
        await s.commit()
        ok = await svc_disable_provider(s, user.id, provider)
        if ok:
            await s.commit()
        return ok
