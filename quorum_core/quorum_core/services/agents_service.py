"""CRUD for DB-backed council agents (used by the desktop Agents settings page).

The Chairman is a protected singleton: it can be edited but not deleted, and new agents are always
council members. Each builtin agent keeps an immutable baseline for "reset to default".
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quorum_core.models import AgentConfig

CHAIRMAN_ROLE = "chairman"
MEMBER_ROLE = "council_member"

# Editable frontmatter fields (everything except key/role/system_prompt/baseline).
EDITABLE_FIELDS = (
    "name",
    "default_provider",
    "default_model",
    "temperature",
    "display_order",
    "owned_sections",
    "output_schema",
)


class AgentError(RuntimeError):
    """Raised for invalid agent edits (bad key, duplicate, deleting the chairman, etc.)."""


def _to_dict(row: AgentConfig) -> dict[str, Any]:
    return {
        "key": row.key,
        "name": row.name,
        "role": row.role,
        "phase": row.phase,
        "default_provider": row.default_provider,
        "default_model": row.default_model,
        "temperature": row.temperature,
        "display_order": row.display_order,
        "owned_sections": list(row.owned_sections or []),
        "output_schema": row.output_schema,
        "system_prompt": row.system_prompt,
        "is_builtin": row.is_builtin,
        "can_delete": row.role != CHAIRMAN_ROLE,
        "can_reset": bool(row.baseline_system_prompt is not None),
    }


async def list_agents(session: AsyncSession) -> list[dict[str, Any]]:
    rows = list(await session.scalars(select(AgentConfig).order_by(AgentConfig.display_order)))
    return [_to_dict(r) for r in rows]


async def get_agent(session: AsyncSession, key: str) -> dict[str, Any] | None:
    row = await session.scalar(select(AgentConfig).where(AgentConfig.key == key))
    return _to_dict(row) if row else None


async def create_agent(
    session: AsyncSession, *, key: str, name: str, system_prompt: str, **fields: Any
) -> dict[str, Any]:
    """Create a new council member. Caller commits."""
    key = (key or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", key or ""):
        raise AgentError("Key must be lowercase letters, digits, or underscores.")
    if not (name or "").strip():
        raise AgentError("Name is required.")
    if not (system_prompt or "").strip():
        raise AgentError("Prompt is required.")
    if await session.scalar(select(AgentConfig).where(AgentConfig.key == key)):
        raise AgentError(f"An agent with key '{key}' already exists.")

    row = AgentConfig(
        key=key,
        name=name.strip(),
        role=MEMBER_ROLE,  # new agents are always council members
        phase="deliberation",
        default_provider=fields.get("default_provider", "anthropic"),
        default_model=fields.get("default_model", "claude-sonnet-4-6"),
        temperature=float(fields.get("temperature", 0.3)),
        display_order=int(fields.get("display_order", 100)),
        owned_sections=list(fields.get("owned_sections", [])),
        output_schema=fields.get("output_schema", "CouncilContribution"),
        system_prompt=system_prompt,
        baseline_system_prompt=None,  # user-added: no shipped baseline to reset to
        baseline_meta=None,
        is_builtin=False,
    )
    session.add(row)
    await session.flush()
    return _to_dict(row)


async def update_agent(
    session: AsyncSession, key: str, *, system_prompt: str | None = None, **fields: Any
) -> dict[str, Any]:
    """Update an agent's prompt and/or editable frontmatter fields. Caller commits."""
    row = await session.scalar(select(AgentConfig).where(AgentConfig.key == key))
    if row is None:
        raise AgentError(f"unknown agent '{key}'")
    if system_prompt is not None:
        if not system_prompt.strip():
            raise AgentError("Prompt cannot be empty.")
        row.system_prompt = system_prompt
    for field in EDITABLE_FIELDS:
        if field in fields and fields[field] is not None:
            value = fields[field]
            if field == "temperature":
                value = float(value)
            elif field == "display_order":
                value = int(value)
            elif field == "owned_sections":
                value = list(value)
            setattr(row, field, value)
    await session.flush()
    return _to_dict(row)


async def delete_agent(session: AsyncSession, key: str) -> None:
    """Delete a council member. The Chairman cannot be deleted. Caller commits."""
    row = await session.scalar(select(AgentConfig).where(AgentConfig.key == key))
    if row is None:
        raise AgentError(f"unknown agent '{key}'")
    if row.role == CHAIRMAN_ROLE:
        raise AgentError("The Chairman cannot be deleted.")
    members = await session.scalar(
        select(func.count()).select_from(AgentConfig).where(AgentConfig.role == MEMBER_ROLE)
    )
    if (members or 0) <= 1:
        raise AgentError("At least one council member is required.")
    await session.delete(row)
    await session.flush()


async def reset_agent(session: AsyncSession, key: str) -> dict[str, Any]:
    """Restore a builtin agent's prompt + frontmatter to its shipped baseline. Caller commits."""
    row = await session.scalar(select(AgentConfig).where(AgentConfig.key == key))
    if row is None:
        raise AgentError(f"unknown agent '{key}'")
    if row.baseline_system_prompt is None or not row.baseline_meta:
        raise AgentError("This agent has no shipped baseline to reset to.")
    meta = row.baseline_meta
    row.system_prompt = row.baseline_system_prompt
    row.name = meta.get("name", row.name)
    row.default_provider = meta.get("default_provider", row.default_provider)
    row.default_model = meta.get("default_model", row.default_model)
    row.temperature = float(meta.get("temperature", row.temperature))
    row.display_order = int(meta.get("order", row.display_order))
    row.owned_sections = list(meta.get("owned_sections", row.owned_sections or []))
    row.output_schema = meta.get("output_schema", row.output_schema)
    await session.flush()
    return _to_dict(row)
