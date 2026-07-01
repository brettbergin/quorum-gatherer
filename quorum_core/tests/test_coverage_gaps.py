"""Coverage tests for catalog, provider, validation, events, migrate, agents_service.

Set an isolated temp SQLite DB and disable test-model mode BEFORE importing quorum_core so the
cached settings / DB engine pick it up. Provider SDK clients are mocked so no network is touched.
"""

from __future__ import annotations

import os
import tempfile

# Configure settings BEFORE importing quorum_core (settings are lru_cache'd, db engine is built
# at import time from the configured URL).
_DB_PATH = os.path.join(tempfile.mkdtemp(prefix="quorum-coverage-"), "test.db")
os.environ["QUORUM_DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
os.environ["QUORUM_USE_TEST_MODEL"] = "0"  # exercise the real (mocked) provider/catalog paths
for _k in (
    "QUORUM_ANTHROPIC_API_KEY",
    "QUORUM_OPENAI_API_KEY",
    "QUORUM_GOOGLE_API_KEY",
    "QUORUM_GROQ_API_KEY",
    "QUORUM_MISTRAL_API_KEY",
    "QUORUM_COHERE_API_KEY",
):
    os.environ.pop(_k, None)

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import quorum_core.agents.catalog as catalog_mod  # noqa: E402
from quorum_core.agents.catalog import CatalogError, fetch_models  # noqa: E402
from quorum_core.agents.provider import (  # noqa: E402
    PROVIDERS,
    ProviderError,
    build_model,
    list_provider_specs,
)
from quorum_core.agents.validation import validate_provider_key  # noqa: E402
from quorum_core.core.db import Base, init_db  # noqa: E402
from quorum_core.core.events import EventBus, event_bus  # noqa: E402
from quorum_core.models import AgentConfig  # noqa: E402
from quorum_core.services import agents_service  # noqa: E402
from quorum_core.services.agents_service import (  # noqa: E402
    AgentError,
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    reset_agent,
    update_agent,
)
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


# --------------------------------------------------------------------------------------
# Fakes for the provider SDK clients used by catalog._fetch
# --------------------------------------------------------------------------------------
class _AsyncList:
    """An async-iterable wrapping a list of model objects (anthropic/google style)."""

    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        async def gen():
            for it in self._items:
                yield it

        return gen()


class _FakeAnthropic:
    def __init__(self, api_key=None):
        self.models = SimpleNamespace(
            list=lambda: _AsyncList(
                [
                    SimpleNamespace(id="claude-opus-4-8", display_name="Claude Opus 4.8"),
                    SimpleNamespace(id="claude-x", display_name=""),  # falls back to id
                ]
            )
        )


class _FakeOpenAI:
    def __init__(self, api_key=None):
        async def _list():
            return SimpleNamespace(
                data=[
                    SimpleNamespace(id="gpt-4o"),
                    SimpleNamespace(id="o3-mini"),
                    SimpleNamespace(id="text-embedding-3-small"),  # filtered out
                ]
            )

        self.models = SimpleNamespace(list=_list)


class _FakeGoogleClient:
    def __init__(self, api_key=None):
        async def _list():
            return _AsyncList(
                [
                    SimpleNamespace(
                        name="models/gemini-2.5-pro",
                        display_name="Gemini 2.5 Pro",
                        supported_actions=["generateContent"],
                    ),
                    SimpleNamespace(  # no generateContent -> skipped
                        name="models/embedding-001",
                        display_name="Embed",
                        supported_actions=["embedContent"],
                    ),
                    SimpleNamespace(  # empty id -> skipped
                        name="models/",
                        display_name="",
                        supported_actions=[],
                    ),
                ]
            )

        self.aio = SimpleNamespace(models=SimpleNamespace(list=_list))


class _FakeGroq:
    def __init__(self, api_key=None):
        async def _list():
            return SimpleNamespace(
                data=[
                    SimpleNamespace(id="llama-3.3-70b-versatile"),
                    SimpleNamespace(id="deepseek-r1-distill-llama-70b"),
                ]
            )

        self.models = SimpleNamespace(list=_list)


class _FakeMistral:
    def __init__(self, api_key=None):
        async def _list_async():
            return SimpleNamespace(
                data=[
                    SimpleNamespace(id="mistral-large-latest", name="Mistral Large"),
                    SimpleNamespace(id="mistral-small-latest", name=""),
                ]
            )

        self.models = SimpleNamespace(list_async=_list_async)


class _FakeCohere:
    def __init__(self, api_key=None):
        async def _list():
            return SimpleNamespace(
                models=[
                    SimpleNamespace(name="command-r-plus", endpoints=["chat"]),
                    SimpleNamespace(name="embed-english", endpoints=["embed"]),  # filtered out
                ]
            )

        self.models = SimpleNamespace(list=_list)


def _patch_sdk(monkeypatch, dotted_module: str, attr: str, fake):
    import importlib

    mod = importlib.import_module(dotted_module)
    monkeypatch.setattr(mod, attr, fake)


def _force_live(monkeypatch):
    """Force the catalog out of test-model mode regardless of other conftests' env."""
    monkeypatch.setattr(catalog_mod, "get_settings", lambda: SimpleNamespace(use_test_model=False))


# --------------------------------------------------------------------------------------
# catalog.py
# --------------------------------------------------------------------------------------
async def test_fetch_models_unknown_provider():
    with pytest.raises(ProviderError):
        await fetch_models("nope", "key")


async def test_fetch_models_requires_key():
    with pytest.raises(CatalogError):
        await fetch_models("anthropic", "")


async def test_fetch_models_test_mode_returns_stub(monkeypatch):
    monkeypatch.setattr(catalog_mod, "get_settings", lambda: SimpleNamespace(use_test_model=True))
    models = await fetch_models("anthropic", "sk-anything")
    ids = {m["id"] for m in models}
    assert "claude-sonnet-4-6" in ids


async def test_fetch_models_anthropic(monkeypatch):
    _force_live(monkeypatch)
    _patch_sdk(monkeypatch, "anthropic", "AsyncAnthropic", _FakeAnthropic)
    models = await fetch_models("anthropic", "sk-test")
    by_id = {m["id"]: m for m in models}
    assert by_id["claude-opus-4-8"]["label"] == "Claude Opus 4.8"
    assert by_id["claude-x"]["label"] == "claude-x"  # blank display_name falls back to id
    assert by_id["claude-opus-4-8"]["supports_reasoning"] is True


async def test_fetch_models_openai_filters_to_chat_models(monkeypatch):
    _force_live(monkeypatch)
    _patch_sdk(monkeypatch, "openai", "AsyncOpenAI", _FakeOpenAI)
    models = await fetch_models("openai", "sk-test")
    ids = {m["id"] for m in models}
    assert ids == {"gpt-4o", "o3-mini"}  # embedding model filtered out


async def test_fetch_models_google(monkeypatch):
    from google import genai

    _force_live(monkeypatch)
    monkeypatch.setattr(genai, "Client", _FakeGoogleClient)
    models = await fetch_models("google", "sk-test")
    ids = {m["id"] for m in models}
    assert ids == {"gemini-2.5-pro"}  # non-generate + empty-id models skipped


async def test_fetch_models_groq(monkeypatch):
    _force_live(monkeypatch)
    _patch_sdk(monkeypatch, "groq", "AsyncGroq", _FakeGroq)
    models = await fetch_models("groq", "sk-test")
    by_id = {m["id"]: m for m in models}
    assert by_id["deepseek-r1-distill-llama-70b"]["supports_reasoning"] is True


async def test_fetch_models_mistral(monkeypatch):
    import mistralai.client as mclient

    _force_live(monkeypatch)
    monkeypatch.setattr(mclient, "Mistral", _FakeMistral)
    models = await fetch_models("mistral", "sk-test")
    by_id = {m["id"]: m for m in models}
    assert by_id["mistral-large-latest"]["label"] == "Mistral Large"
    assert by_id["mistral-small-latest"]["label"] == "mistral-small-latest"


async def test_fetch_models_cohere(monkeypatch):
    _force_live(monkeypatch)
    _patch_sdk(monkeypatch, "cohere", "AsyncClientV2", _FakeCohere)
    models = await fetch_models("cohere", "sk-test")
    ids = {m["id"] for m in models}
    assert ids == {"command-r-plus"}  # non-chat endpoint filtered out


async def test_fetch_models_wraps_provider_error_as_catalog_error(monkeypatch):
    class _Boom:
        def __init__(self, api_key=None):
            raise RuntimeError("bad auth\nmore detail")

    _force_live(monkeypatch)
    _patch_sdk(monkeypatch, "anthropic", "AsyncAnthropic", _Boom)
    with pytest.raises(CatalogError) as ei:
        await fetch_models("anthropic", "sk-test")
    assert "bad auth" in str(ei.value)


async def test_fetch_models_timeout(monkeypatch):
    async def _slow(*a, **k):
        raise TimeoutError

    _force_live(monkeypatch)
    monkeypatch.setattr(catalog_mod, "_fetch", _slow)
    with pytest.raises(CatalogError, match="timed out"):
        await fetch_models("anthropic", "sk-test")


# --------------------------------------------------------------------------------------
# provider.py build_model + helpers
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "provider,model",
    [
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-4o"),
        ("google", "gemini-2.0-flash"),
        ("groq", "llama-3.3-70b-versatile"),
        ("mistral", "mistral-large-latest"),
        ("cohere", "command-r-plus"),
    ],
)
def test_build_model_each_provider_with_key(provider, model):
    from pydantic_ai.models import Model

    assert isinstance(build_model(provider, model, "dummy-key"), Model)


def test_build_model_unknown_provider():
    with pytest.raises(ProviderError):
        build_model("nope", "model", "key")


def test_build_model_anthropic_without_key_uses_env_provider(monkeypatch):
    # Force the no-key branch with a fallback env key so AnthropicProvider() finds a key.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    from pydantic_ai.models import Model

    assert isinstance(build_model("anthropic", "claude-sonnet-4-6", None), Model)


def test_list_provider_specs_covers_all():
    specs = list_provider_specs()
    assert {s.key for s in specs} == set(PROVIDERS)


def test_build_reasoning_settings_branches():
    from quorum_core.agents.provider import build_reasoning_settings

    # Unknown provider / blank raw -> {}
    assert build_reasoning_settings("nope", "m", "high") == {}
    assert build_reasoning_settings("openai", "o3-mini", None) == {}
    # Model that doesn't support reasoning -> {}
    assert build_reasoning_settings("openai", "gpt-4o", "high") == {}
    # effort kind, valid + invalid + "none"
    assert build_reasoning_settings("openai", "o3-mini", "high") == {
        "openai_reasoning_effort": "high"
    }
    assert build_reasoning_settings("openai", "o3-mini", "bogus") == {}
    # "off" is not in openai's efforts and short-circuits to {}
    assert build_reasoning_settings("openai", "o3-mini", "off") == {}
    # groq lists "none" as a real effort value, so it is emitted (not dropped)
    assert build_reasoning_settings("groq", "qwen3-32b", "none") == {
        "groq_reasoning_effort": "none"
    }
    # thinking_budget: anthropic shape + clamp
    spec = PROVIDERS["anthropic"].reasoning
    assert build_reasoning_settings("anthropic", "claude-opus-4-8", str(spec.budget_max + 1)) == {
        "anthropic_thinking": {"type": "enabled", "budget_tokens": spec.budget_max}
    }
    # thinking_budget: google shape
    assert build_reasoning_settings("google", "gemini-2.5-pro", "4096") == {
        "google_thinking_config": {"thinking_budget": 4096, "include_thoughts": False}
    }
    # thinking_budget: non-numeric -> {}, and <=0 -> {}
    assert build_reasoning_settings("anthropic", "claude-opus-4-8", "abc") == {}
    assert build_reasoning_settings("anthropic", "claude-opus-4-8", "0") == {}


def test_resolve_runtime_model_prefers_default_provider():
    from quorum_core.agents.provider import RuntimeModel, resolve_runtime_model

    configured = {
        "anthropic": {"api_key": "sk-a", "default_model": "claude-haiku-4-5", "enabled": True}
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        configured=configured,
    )
    assert isinstance(rt, RuntimeModel)
    assert rt.provider == "anthropic"
    assert rt.model == "claude-haiku-4-5"
    assert rt.api_key == "sk-a"


def test_resolve_runtime_model_falls_back_and_skips_disabled(monkeypatch):
    import quorum_core.agents.provider as prov_mod
    from quorum_core.agents.provider import resolve_runtime_model

    # No env fallback keys present.
    monkeypatch.setattr(
        prov_mod,
        "get_settings",
        lambda: SimpleNamespace(
            anthropic_api_key=None,
            openai_api_key=None,
            google_api_key=None,
            groq_api_key=None,
            mistral_api_key=None,
            cohere_api_key=None,
        ),
    )
    configured = {
        "anthropic": {"enabled": False, "api_key": "sk-a"},  # disabled -> skipped
        "openai": {"api_key": "", "enabled": True},  # no key -> skipped
        "groq": {"api_key": "sk-g", "default_model": "llama-3.1-8b-instant", "enabled": True},
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        configured=configured,
    )
    assert rt.provider == "groq"
    assert rt.model == "llama-3.1-8b-instant"


def test_resolve_runtime_model_chairman_branch():
    from quorum_core.agents.provider import resolve_runtime_model

    configured = {
        "anthropic": {
            "api_key": "sk-a",
            "default_model": "claude-haiku-4-5",
            "chairman_model": "claude-opus-4-8",
            "chairman_reasoning": "9000",
            "enabled": True,
        }
    }
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        configured=configured,
        is_chairman=True,
    )
    assert rt.model == "claude-opus-4-8"
    assert rt.model_settings == {"anthropic_thinking": {"type": "enabled", "budget_tokens": 9000}}


def test_resolve_runtime_model_no_config_returns_defaults_without_key(monkeypatch):
    import quorum_core.agents.provider as prov_mod
    from quorum_core.agents.provider import resolve_runtime_model

    monkeypatch.setattr(
        prov_mod,
        "get_settings",
        lambda: SimpleNamespace(
            anthropic_api_key=None,
            openai_api_key=None,
            google_api_key=None,
            groq_api_key=None,
            mistral_api_key=None,
            cohere_api_key=None,
        ),
    )
    rt = resolve_runtime_model(
        default_provider="anthropic",
        default_model="claude-sonnet-4-6",
        configured={},
    )
    assert rt.provider == "anthropic"
    assert rt.model == "claude-sonnet-4-6"
    assert rt.api_key is None


# --------------------------------------------------------------------------------------
# validation.py
# --------------------------------------------------------------------------------------
async def test_validate_test_model_mode_is_noop(monkeypatch):
    import quorum_core.agents.validation as val_mod

    monkeypatch.setattr(val_mod, "get_settings", lambda: SimpleNamespace(use_test_model=True))
    ok, err = await validate_provider_key("anthropic", "claude-sonnet-4-6", "key")
    assert ok is True and err is None


async def test_validate_success(monkeypatch):
    import quorum_core.agents.validation as val_mod

    monkeypatch.setattr(val_mod, "get_settings", lambda: SimpleNamespace(use_test_model=False))
    monkeypatch.setattr(val_mod, "build_model", lambda *a, **k: object())

    class _FakeAgent:
        def __init__(self, *a, **k):
            pass

        async def run(self, prompt):
            return SimpleNamespace(output="ok")

    monkeypatch.setattr(val_mod, "Agent", _FakeAgent)
    ok, err = await validate_provider_key("anthropic", "claude-sonnet-4-6", "key")
    assert ok is True and err is None


async def test_validate_timeout(monkeypatch):
    import quorum_core.agents.validation as val_mod

    monkeypatch.setattr(val_mod, "get_settings", lambda: SimpleNamespace(use_test_model=False))
    monkeypatch.setattr(val_mod, "build_model", lambda *a, **k: object())

    class _SlowAgent:
        def __init__(self, *a, **k):
            pass

        async def run(self, prompt):
            raise TimeoutError

    monkeypatch.setattr(val_mod, "Agent", _SlowAgent)
    ok, err = await validate_provider_key("anthropic", "claude-sonnet-4-6", "key")
    assert ok is False and err == "validation request timed out"


async def test_validate_failure_surfaces_error(monkeypatch):
    import quorum_core.agents.validation as val_mod

    monkeypatch.setattr(val_mod, "get_settings", lambda: SimpleNamespace(use_test_model=False))

    def _boom(*a, **k):
        raise RuntimeError("invalid api key\nsecond line")

    monkeypatch.setattr(val_mod, "build_model", _boom)
    ok, err = await validate_provider_key("anthropic", "claude-sonnet-4-6", "bad")
    assert ok is False
    assert err == "invalid api key"  # only first line, no traceback


# --------------------------------------------------------------------------------------
# core/events.py
# --------------------------------------------------------------------------------------
async def test_event_bus_subscribe_publish_unsubscribe():
    bus = EventBus()
    q1 = bus.subscribe("chat1")
    q2 = bus.subscribe("chat1")
    await bus.publish("chat1", {"n": 1})
    assert (await q1.get())["n"] == 1
    assert (await q2.get())["n"] == 1

    bus.unsubscribe("chat1", q1)
    bus.unsubscribe("chat1", q2)
    # Last unsubscribe removes the key entirely.
    assert "chat1" not in bus._subscribers
    # Unsubscribing an unknown queue/chat is a no-op.
    bus.unsubscribe("missing", q1)
    # Publishing with no subscribers is a no-op.
    await bus.publish("chat1", {"n": 2})


async def test_event_bus_stream_yields_then_cleans_up():
    import asyncio

    bus = EventBus()
    agen = bus.stream("chatX")
    # stream() subscribes lazily inside __anext__; start consuming on a task so the subscription
    # exists, then publish once a subscriber is registered.
    next_task = asyncio.ensure_future(agen.__anext__())
    while not bus._subscribers.get("chatX"):
        await asyncio.sleep(0)
    await bus.publish("chatX", {"x": 2})
    evt = await asyncio.wait_for(next_task, timeout=5)
    assert evt["x"] == 2
    await agen.aclose()  # triggers the finally -> unsubscribe
    assert "chatX" not in bus._subscribers


def test_module_level_event_bus_singleton():
    assert isinstance(event_bus, EventBus)


# --------------------------------------------------------------------------------------
# migrate.py
# --------------------------------------------------------------------------------------
def test_upgrade_to_head_creates_tables(tmp_path):
    import sqlite3

    from quorum_core.migrate import make_alembic_config, upgrade_to_head

    db_file = tmp_path / "migrated.db"
    url = f"sqlite+aiosqlite:///{db_file}"  # alembic env.py uses an async engine

    cfg = make_alembic_config(url)
    assert cfg.get_main_option("sqlalchemy.url") == url

    upgrade_to_head(url)

    conn = sqlite3.connect(db_file)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "agent_configs" in names
    assert "alembic_version" in names


# --------------------------------------------------------------------------------------
# services/agents_service.py
# --------------------------------------------------------------------------------------
@pytest_asyncio.fixture
async def session():
    """Fresh tables on a dedicated engine bound to the isolated temp DB."""
    engine = create_async_engine(os.environ["QUORUM_DATABASE_URL"], future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
    await engine.dispose()


def _chairman(**kw):
    base = {
        "key": "chairman",
        "name": "The Chairman",
        "role": agents_service.CHAIRMAN_ROLE,
        "phase": "synthesis",
        "system_prompt": "synthesize",
        "baseline_system_prompt": "baseline chairman",
        "baseline_meta": {"name": "Baseline Chair", "temperature": 0.5, "order": 3},
        "is_builtin": True,
    }
    base.update(kw)
    return AgentConfig(**base)


def _member(key, **kw):
    base = {
        "key": key,
        "name": f"Member {key}",
        "role": agents_service.MEMBER_ROLE,
        "phase": "deliberation",
        "system_prompt": "contribute",
        "is_builtin": False,
    }
    base.update(kw)
    return AgentConfig(**base)


async def test_create_and_get_and_list_agent(session):
    session.add(_chairman())
    await session.flush()

    created = await create_agent(
        session,
        key="analyst",
        name="The Analyst",
        system_prompt="analyze",
        temperature="0.7",
        display_order="5",
        owned_sections=("a", "b"),
    )
    assert created["key"] == "analyst"
    assert created["role"] == agents_service.MEMBER_ROLE
    assert created["can_delete"] is True
    assert created["temperature"] == 0.7
    assert created["owned_sections"] == ["a", "b"]

    got = await get_agent(session, "analyst")
    assert got["name"] == "The Analyst"
    assert await get_agent(session, "missing") is None

    agents = await list_agents(session)
    assert {a["key"] for a in agents} == {"chairman", "analyst"}


async def test_create_agent_validation_errors(session):
    with pytest.raises(AgentError, match="lowercase"):
        await create_agent(session, key="Bad Key!", name="x", system_prompt="p")
    with pytest.raises(AgentError, match="Name is required"):
        await create_agent(session, key="ok", name="  ", system_prompt="p")
    with pytest.raises(AgentError, match="Prompt is required"):
        await create_agent(session, key="ok", name="Ok", system_prompt="  ")

    await create_agent(session, key="dup", name="Dup", system_prompt="p")
    with pytest.raises(AgentError, match="already exists"):
        await create_agent(session, key="dup", name="Dup2", system_prompt="p")


async def test_update_agent_fields_and_errors(session):
    session.add(_member("analyst"))
    await session.flush()

    updated = await update_agent(
        session,
        "analyst",
        system_prompt="new prompt",
        name="Renamed",
        temperature="0.9",
        display_order="2",
        owned_sections=("x",),
        default_model=None,  # None values are ignored
    )
    assert updated["system_prompt"] == "new prompt"
    assert updated["name"] == "Renamed"
    assert updated["temperature"] == 0.9
    assert updated["display_order"] == 2
    assert updated["owned_sections"] == ["x"]

    with pytest.raises(AgentError, match="unknown agent"):
        await update_agent(session, "ghost", name="x")
    with pytest.raises(AgentError, match="cannot be empty"):
        await update_agent(session, "analyst", system_prompt="   ")


async def test_delete_agent_rules(session):
    session.add(_chairman())
    session.add(_member("m1"))
    session.add(_member("m2"))
    await session.flush()

    with pytest.raises(AgentError, match="unknown agent"):
        await delete_agent(session, "ghost")
    with pytest.raises(AgentError, match="Chairman cannot be deleted"):
        await delete_agent(session, "chairman")

    # Two members -> deleting one is fine.
    await delete_agent(session, "m2")
    # One member left -> guard kicks in.
    with pytest.raises(AgentError, match="At least one council member"):
        await delete_agent(session, "m1")


async def test_reset_agent(session):
    session.add(_chairman(name="Edited", temperature=0.1, display_order=99))
    session.add(_member("plain"))  # no baseline
    await session.flush()

    reset = await reset_agent(session, "chairman")
    assert reset["name"] == "Baseline Chair"
    assert reset["system_prompt"] == "baseline chairman"
    assert reset["temperature"] == 0.5
    assert reset["display_order"] == 3

    with pytest.raises(AgentError, match="unknown agent"):
        await reset_agent(session, "ghost")
    with pytest.raises(AgentError, match="no shipped baseline"):
        await reset_agent(session, "plain")


# --------------------------------------------------------------------------------------
# core/db init_db smoke (exercises the shared engine against the isolated temp DB)
# --------------------------------------------------------------------------------------
async def test_init_db_creates_tables():
    await init_db()
    from quorum_core.core.db import engine

    async with engine.begin() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        names = {r[0] for r in rows}
    assert "agent_configs" in names
