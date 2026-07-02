#!/usr/bin/env python3
"""Bump the quorum-gatherer version across every canonical location.

The root ``pyproject.toml`` ``[project].version`` is the single source of truth.
This keeps the following in lockstep with it:

  - pyproject.toml                          (workspace root)
  - desktop/pyproject.toml                  (quorum-desktop)
  - quorum_core/quorum_core/__init__.py     (__version__ — drives quorum_core's
                                             dynamic hatch version)

Usage:
    bump_version.py [major|minor|patch]     # default: patch

Prints the new version (e.g. ``0.1.1``) to stdout so CI can capture it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files carrying a literal ``version = "X.Y.Z"`` under [project].
PYPROJECTS = [
    ROOT / "pyproject.toml",
    ROOT / "desktop" / "pyproject.toml",
]
# quorum_core derives its version dynamically from __version__ here.
INIT = ROOT / "quorum_core" / "quorum_core" / "__init__.py"

PYPROJECT_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"', re.MULTILINE)
INIT_RE = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"', re.MULTILINE)


def current_version() -> tuple[int, int, int]:
    text = PYPROJECTS[0].read_text()
    m = PYPROJECT_RE.search(text)
    if not m:
        sys.exit(f"error: no version found in {PYPROJECTS[0]}")
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def _replace(path: Path, pattern: re.Pattern[str], replacement: str) -> None:
    text = path.read_text()
    new_text, count = pattern.subn(replacement, text, count=1)
    if count == 0:
        sys.exit(f"error: no version line to update in {path}")
    path.write_text(new_text)


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if part not in {"major", "minor", "patch"}:
        sys.exit(f"error: invalid bump part {part!r} (expected major|minor|patch)")

    new_version = ".".join(str(n) for n in bump(current_version(), part))

    for pyproject in PYPROJECTS:
        _replace(pyproject, PYPROJECT_RE, f'version = "{new_version}"')
    _replace(INIT, INIT_RE, f'__version__ = "{new_version}"')

    print(new_version)


if __name__ == "__main__":
    main()
