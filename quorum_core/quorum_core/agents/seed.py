"""One-time ETL of the shipped `*.agent.md` files into the `agent_configs` table.

After this seed runs, the desktop app reads agents from the DB (see
`loader.build_registry_from_db`) and users can edit them. The shared charter stays file-sourced.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quorum_core.agents.definition import AgentDefinition
from quorum_core.agents.loader import AGENT_GLOB, parse_frontmatter
from quorum_core.core.config import get_settings
from quorum_core.models import AgentConfig


def _row_from_file(path: Path) -> AgentConfig:
    data, body = parse_frontmatter(path.read_text(encoding="utf-8"), source=path.name)
    # Validate/normalize through AgentDefinition so defaults match the file-based loader exactly.
    defn = AgentDefinition(**data, system_prompt=body, charter="")
    return AgentConfig(
        key=defn.key,
        name=defn.name,
        role=str(defn.role),
        phase=str(defn.phase),
        default_provider=defn.default_provider,
        default_model=defn.default_model,
        temperature=defn.temperature,
        display_order=defn.order,
        owned_sections=list(defn.owned_sections),
        output_schema=defn.output_schema,
        system_prompt=defn.system_prompt,
        baseline_system_prompt=defn.system_prompt,
        baseline_meta=data,
        is_builtin=True,
    )


async def seed_agents(session: AsyncSession, directory: str | Path | None = None) -> int:
    """Insert shipped agents into `agent_configs` if the table is empty. Returns rows inserted.

    Idempotent: does nothing once any agent rows exist. Caller commits.
    """
    existing = await session.scalar(select(func.count()).select_from(AgentConfig))
    if existing:
        return 0

    settings = get_settings()
    directory = Path(directory) if directory else settings.agent_prompts_dir
    if not directory.is_dir():
        return 0

    rows = [_row_from_file(p) for p in sorted(directory.glob(AGENT_GLOB))]
    for row in rows:
        session.add(row)
    await session.flush()
    return len(rows)
