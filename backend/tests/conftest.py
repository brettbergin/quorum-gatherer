"""Test fixtures: a temp SQLite DB and an in-process ASGI client in test-model mode."""

import os
import tempfile

# Configure the app BEFORE importing it (settings are cached on first access).
_db = os.path.join(tempfile.mkdtemp(prefix="quorum-test-"), "test.db")
os.environ["QUORUM_DATABASE_URL"] = f"sqlite+aiosqlite:///{_db}"
os.environ["QUORUM_USE_TEST_MODEL"] = "1"
os.environ.pop("QUORUM_ANTHROPIC_API_KEY", None)

import pytest_asyncio  # noqa: E402
from app.main import app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from quorum_core.agents.loader import load_agents  # noqa: E402
from quorum_core.core.db import init_db  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await init_db()
    app.state.agents = load_agents()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
