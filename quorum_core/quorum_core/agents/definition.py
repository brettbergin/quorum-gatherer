"""The validated, in-memory representation of an agent definition file."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    council_member = "council_member"
    chairman = "chairman"


class AgentPhase(StrEnum):
    deliberation = "deliberation"  # Phase A
    synthesis = "synthesis"  # Phase B


class AgentDefinition(BaseModel):
    """One agent, parsed from a `*.agent.md` file (frontmatter + prompt body)."""

    key: str
    name: str
    role: AgentRole = AgentRole.council_member
    phase: AgentPhase = AgentPhase.deliberation
    default_provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-6"
    temperature: float = 0.3
    order: int = 100  # display / execution ordering among members
    owned_sections: list[str] = Field(default_factory=list)
    output_schema: str = "CouncilContribution"

    system_prompt: str  # the file body (role instructions)
    charter: str = ""  # shared prefix applied to every agent

    def full_system_prompt(self) -> str:
        """Charter (shared) + this agent's role body = the effective system prompt."""
        parts = [p for p in (self.charter.strip(), self.system_prompt.strip()) if p]
        return "\n\n".join(parts)
