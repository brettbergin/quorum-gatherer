"""Agent loader: validates the shipped files and rejects malformed ones."""

from pathlib import Path

import pytest
from quorum_core.agents.definition import AgentRole
from quorum_core.agents.loader import AgentLoadError, load_agents, parse_frontmatter

CHARTER = "Shared charter text."
GOOD_MEMBER = """---
key: m1
name: Member One
role: council_member
order: 1
---
You are member one.
"""
GOOD_CHAIR = """---
key: chairman
name: The Chairman
role: chairman
---
You synthesize.
"""


def _write(dir: Path, name: str, text: str) -> None:
    (dir / name).write_text(text, encoding="utf-8")


def test_ships_nine_agents_with_one_chairman():
    registry = load_agents()
    assert len(registry) == 9
    assert len(registry.members) == 8
    assert registry.chairman.role == AgentRole.chairman
    # members are ordered by their `order` field
    assert [m.key for m in registry.members][0] == "analyst"


def test_charter_is_prefixed_to_every_agent():
    registry = load_agents()
    for agent in registry.all():
        assert agent.full_system_prompt().startswith("# Product Strategy Council")


def test_parse_frontmatter_requires_delimiters():
    with pytest.raises(AgentLoadError):
        parse_frontmatter("no frontmatter here", source="x")


def test_loads_minimal_valid_dir(tmp_path: Path):
    _write(tmp_path, "_charter.md", CHARTER)
    _write(tmp_path, "m1.agent.md", GOOD_MEMBER)
    _write(tmp_path, "chairman.agent.md", GOOD_CHAIR)
    registry = load_agents(tmp_path)
    assert len(registry) == 2
    assert registry.get("m1").full_system_prompt().startswith(CHARTER)


def test_requires_exactly_one_chairman(tmp_path: Path):
    _write(tmp_path, "m1.agent.md", GOOD_MEMBER)  # no chairman
    with pytest.raises(AgentLoadError, match="chairman"):
        load_agents(tmp_path)


def test_duplicate_keys_rejected(tmp_path: Path):
    _write(tmp_path, "a.agent.md", GOOD_MEMBER)
    _write(tmp_path, "b.agent.md", GOOD_MEMBER)  # same key m1
    _write(tmp_path, "chairman.agent.md", GOOD_CHAIR)
    with pytest.raises(AgentLoadError, match="duplicate"):
        load_agents(tmp_path)


def test_empty_body_rejected(tmp_path: Path):
    _write(tmp_path, "chairman.agent.md", GOOD_CHAIR)
    _write(tmp_path, "bad.agent.md", "---\nkey: x\nname: X\nrole: council_member\n---\n")
    with pytest.raises(AgentLoadError, match="empty"):
        load_agents(tmp_path)
