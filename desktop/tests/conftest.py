"""Desktop test fixtures: headless (offscreen) Qt, a temp SQLite DB in test-model mode.

Importing any PySide6 module spins up a platform plugin, so QT_QPA_PLATFORM must be set
before that happens — hence at module import time here. pytest-qt provides the `qtbot`
fixture and a shared QApplication for the GUI tests.
"""

import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Configure persistence BEFORE importing anything that builds the engine from settings.
_db_dir = tempfile.mkdtemp(prefix="quorum-desktop-test-")
os.environ["QUORUM_DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_db_dir, 'test.db')}"
os.environ["QUORUM_USE_TEST_MODEL"] = "1"
os.environ.pop("QUORUM_ANTHROPIC_API_KEY", None)

import pytest_asyncio  # noqa: E402
from quorum_core.core.db import init_db  # noqa: E402


@pytest_asyncio.fixture
async def db():
    """Create the schema and seed agents so engine calls have a working database."""
    from quorum_desktop import engine

    await init_db()
    await engine.ensure_agents()
    return engine
