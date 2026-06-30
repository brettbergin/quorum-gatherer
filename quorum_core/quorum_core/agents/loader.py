"""Read and validate agent definition files from the dedicated `agent_prompts/` folder.

Each `*.agent.md` file is YAML frontmatter + a Markdown body. The shared `_charter.md`
(council intro + Context Usage + Guidelines) is prepended to every agent's system prompt.
A malformed or inconsistent set of files raises `AgentLoadError` so the app fails fast.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from quorum_core.agents.definition import AgentDefinition, AgentRole
from quorum_core.core.config import get_settings

CHARTER_FILE = "_charter.md"
AGENT_GLOB = "*.agent.md"


class AgentLoadError(RuntimeError):
    """Raised when the agent_prompts/ folder is missing, malformed, or inconsistent."""


def parse_frontmatter(text: str, *, source: str = "<string>") -> tuple[dict, str]:
    """Split a `---\\nYAML\\n---\\nbody` document into (metadata, body)."""
    stripped = text.lstrip("﻿")
    if not stripped.startswith("---"):
        raise AgentLoadError(f"{source}: missing YAML frontmatter (must start with '---')")
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        raise AgentLoadError(f"{source}: malformed frontmatter (need opening and closing '---')")
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise AgentLoadError(f"{source}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentLoadError(f"{source}: frontmatter must be a mapping")
    return data, parts[2].strip()


class AgentRegistry:
    """The loaded council: the chairman plus ordered council members."""

    def __init__(self, agents: list[AgentDefinition]) -> None:
        self._by_key = {a.key: a for a in agents}
        self.chairman: AgentDefinition = next(a for a in agents if a.role == AgentRole.chairman)
        self.members: list[AgentDefinition] = sorted(
            (a for a in agents if a.role == AgentRole.council_member),
            key=lambda a: (a.order, a.name),
        )

    def get(self, key: str) -> AgentDefinition:
        return self._by_key[key]

    def all(self) -> list[AgentDefinition]:
        return [*self.members, self.chairman]

    def __len__(self) -> int:
        return len(self._by_key)


def load_agents(directory: str | Path | None = None) -> AgentRegistry:
    settings = get_settings()
    directory = Path(directory) if directory else settings.agent_prompts_dir
    if not directory.is_dir():
        raise AgentLoadError(f"agent_prompts directory not found: {directory}")

    charter_path = directory / CHARTER_FILE
    charter = charter_path.read_text(encoding="utf-8") if charter_path.exists() else ""

    agents: list[AgentDefinition] = []
    for path in sorted(directory.glob(AGENT_GLOB)):
        data, body = parse_frontmatter(path.read_text(encoding="utf-8"), source=path.name)
        if not body:
            raise AgentLoadError(f"{path.name}: empty prompt body")
        try:
            agents.append(AgentDefinition(**data, system_prompt=body, charter=charter))
        except ValidationError as exc:
            raise AgentLoadError(f"{path.name}: invalid frontmatter: {exc}") from exc

    if not agents:
        raise AgentLoadError(f"no {AGENT_GLOB} files found in {directory}")

    keys = [a.key for a in agents]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        raise AgentLoadError(f"duplicate agent keys: {sorted(duplicates)}")

    chairmen = [a for a in agents if a.role == AgentRole.chairman]
    if len(chairmen) != 1:
        raise AgentLoadError(f"exactly one chairman required, found {len(chairmen)}")

    return AgentRegistry(agents)


def _read_charter(directory: str | Path | None = None) -> str:
    directory = Path(directory) if directory else get_settings().agent_prompts_dir
    charter_path = Path(directory) / CHARTER_FILE
    return charter_path.read_text(encoding="utf-8") if charter_path.exists() else ""


async def build_registry_from_db(session, directory: str | Path | None = None) -> AgentRegistry:
    """Build the council registry from `agent_configs` rows (charter merged from the file).

    Used by the desktop runtime after the prompts have been ETL'd into the DB. Raises
    `AgentLoadError` if the roster is inconsistent (no/many chairmen, no agents).
    """
    from sqlalchemy import select

    from quorum_core.models import AgentConfig

    charter = _read_charter(directory)
    rows = list(await session.scalars(select(AgentConfig)))
    if not rows:
        raise AgentLoadError("no agent_configs rows; run seed_agents() first")

    agents: list[AgentDefinition] = []
    for r in rows:
        try:
            agents.append(
                AgentDefinition(
                    key=r.key,
                    name=r.name,
                    role=r.role,
                    phase=r.phase,
                    default_provider=r.default_provider,
                    default_model=r.default_model,
                    temperature=r.temperature,
                    order=r.display_order,
                    owned_sections=list(r.owned_sections or []),
                    output_schema=r.output_schema,
                    system_prompt=r.system_prompt,
                    charter=charter,
                )
            )
        except ValidationError as exc:
            raise AgentLoadError(f"agent '{r.key}': invalid config: {exc}") from exc

    chairmen = [a for a in agents if a.role == AgentRole.chairman]
    if len(chairmen) != 1:
        raise AgentLoadError(f"exactly one chairman required, found {len(chairmen)}")
    return AgentRegistry(agents)
