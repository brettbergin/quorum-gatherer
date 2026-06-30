"""Read-only listing of the configured council agents (from agent_prompts/)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from quorum_core.agents.loader import load_agents

from app.schemas.api import AgentInfo

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents(request: Request) -> list[AgentInfo]:
    registry = getattr(request.app.state, "agents", None) or load_agents()
    return [
        AgentInfo(
            key=a.key,
            name=a.name,
            role=str(a.role),
            phase=str(a.phase),
            order=a.order,
            default_provider=a.default_provider,
            default_model=a.default_model,
            owned_sections=a.owned_sections,
        )
        for a in registry.all()
    ]
