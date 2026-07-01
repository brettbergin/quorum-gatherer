"""Headless GUI tests for the desktop page/panel widgets.

These exercise constructors plus synchronous render/populate/toggle helpers, and drive the
async handlers directly (awaiting them) with the engine/updater functions patched so nothing
needs a live qasync loop or the network. The widgets that schedule work in __init__ via
``_spawn``/``asyncio.ensure_future`` are constructed with that scheduling patched out, then
their coroutines are awaited explicitly.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from quorum_desktop.widgets import agents_page as agents_mod
from quorum_desktop.widgets import providers_page as providers_mod
from quorum_desktop.widgets import updates_page as updates_mod
from quorum_desktop.widgets.agent_panel import AgentPanel
from quorum_desktop.widgets.agents_page import AgentsPage
from quorum_desktop.widgets.composer import Composer
from quorum_desktop.widgets.markdown_view import MarkdownView
from quorum_desktop.widgets.providers_page import ProvidersPage, _ModelReasoningField
from quorum_desktop.widgets.updates_page import UpdatesPage


@contextmanager
def _no_spawn():
    """Neutralise the fire-and-forget scheduling done during widget construction."""
    with patch("asyncio.ensure_future", lambda coro: None):
        yield


# --------------------------------------------------------------------------- fixtures / data


def _effort_spec() -> dict:
    return {
        "key": "openai",
        "label": "OpenAI",
        "default_model": "gpt-x",
        "suggested": ["gpt-x"],
        "reasoning": {
            "kind": "effort",
            "settings_key": "reasoning_effort",
            "efforts": ["low", "medium", "high"],
            "budget_min": 0,
            "budget_max": 0,
            "budget_default": 0,
            "model_pattern": r"^o\d",
        },
    }


def _budget_spec() -> dict:
    return {
        "key": "anthropic",
        "label": "Anthropic",
        "default_model": "claude-x",
        "suggested": ["claude-x"],
        "reasoning": {
            "kind": "thinking_budget",
            "settings_key": "thinking_budget",
            "efforts": [],
            "budget_min": 1024,
            "budget_max": 64000,
            "budget_default": 4096,
            "model_pattern": r"claude",
        },
    }


def _none_spec() -> dict:
    return {
        "key": "plain",
        "label": "Plain",
        "default_model": "m1",
        "suggested": ["m1"],
        "reasoning": {
            "kind": "none",
            "settings_key": "",
            "efforts": [],
            "budget_min": 0,
            "budget_max": 0,
            "budget_default": 0,
            "model_pattern": "",
        },
    }


def _catalog() -> list[dict]:
    return [
        {"id": "o1", "label": "O1", "supports_reasoning": True},
        {"id": "gpt-x", "label": "GPT X", "supports_reasoning": False},
    ]


# --------------------------------------------------------------------------- MarkdownView


def test_markdown_view_renders_all_block_types(qtbot):
    w = MarkdownView()
    qtbot.addWidget(w)
    w.setMarkdown("# H1\n\n## H2\n\n### H3\n\nA paragraph of text.\n\n- one\n- two\n\nmore text")
    assert "H1" in w.toPlainText()
    # Re-render and empty path.
    w.setMarkdown("")
    w.setMarkdown(None)  # type accepts None via "or"
    assert w.toPlainText() == ""


# --------------------------------------------------------------------------- AgentPanel


def test_agent_panel_lifecycle(qtbot):
    panel = AgentPanel("Strategist", agent_key="strategist")
    qtbot.addWidget(panel)

    assert panel.is_active() is True
    panel.set_active(False)
    assert panel.is_active() is False
    panel.set_active(True)

    panel.set_chatted(True)
    panel.set_started("openai", "gpt-x")
    panel.append_token("hel")
    panel.append_token("lo")
    assert "hello" in panel.current_text()

    panel.set_complete("final answer")
    assert panel.current_text() == "final answer"

    panel.set_failed("boom")
    assert "boom" in panel.current_text()

    panel.reset()
    assert panel.current_text() == ""


def test_agent_panel_hydrate_variants(qtbot):
    for status, text, error in [
        ("completed", "done", None),
        ("failed", None, "err"),
        ("running", "partial", None),
        ("pending", None, None),
    ]:
        panel = AgentPanel("A", agent_key="a")
        qtbot.addWidget(panel)
        panel.hydrate(status, text, "openai", "gpt-x", error)


def test_agent_panel_badge_click_emits(qtbot):
    panel = AgentPanel("A", agent_key="a")
    qtbot.addWidget(panel)
    captured: list[str] = []
    panel.details_requested.connect(captured.append)
    panel._on_badge_clicked()
    assert captured == ["a"]

    # Empty key: no emission.
    panel2 = AgentPanel("B", agent_key="")
    qtbot.addWidget(panel2)
    panel2.details_requested.connect(lambda k: captured.append("never"))
    panel2._on_badge_clicked()
    assert "never" not in captured


def test_agent_panel_active_toggle_signal(qtbot):
    panel = AgentPanel("A", agent_key="a")
    qtbot.addWidget(panel)
    events: list[tuple[str, bool]] = []
    panel.active_toggled.connect(lambda k, on: events.append((k, on)))
    panel._active.setChecked(False)
    assert ("a", False) in events


# --------------------------------------------------------------------------- Composer


def test_composer_submit_and_state(qtbot):
    c = Composer()
    qtbot.addWidget(c)

    submitted: list[str] = []
    c.submit.connect(submitted.append)

    # Empty -> button disabled, submit no-op.
    assert c._convene.isEnabled() is False
    c._on_submit()
    assert submitted == []

    c.set_idea("Launch a new product line")
    assert c._convene.isEnabled() is True
    c._on_submit()
    assert submitted == ["Launch a new product line"]

    # Running disables convene even with text.
    c.set_running(True)
    assert c._convene.isEnabled() is False
    assert c._convene.text() == "Council in session…"
    c.set_running(False)
    assert c._convene.text() == "Begin deliberation"

    c.set_documents(["a.md", "b.txt"])
    assert "a.md" in c._docs.text()


def test_composer_pick_file_emits(qtbot):
    c = Composer()
    qtbot.addWidget(c)
    uploaded: list[str] = []
    c.upload.connect(uploaded.append)

    with patch(
        "quorum_desktop.widgets.composer.QFileDialog.getOpenFileName",
        return_value=("/tmp/doc.md", ""),
    ):
        c._pick_file()
    assert uploaded == ["/tmp/doc.md"]

    # Cancelled dialog -> nothing emitted.
    with patch(
        "quorum_desktop.widgets.composer.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        c._pick_file()
    assert uploaded == ["/tmp/doc.md"]


# --------------------------------------------------------------------------- _ModelReasoningField


def test_model_reasoning_field_effort(qtbot):
    f = _ModelReasoningField("Members")
    qtbot.addWidget(f)
    spec = _effort_spec()
    f.configure(spec)
    # Preview a stored model that matches the reasoning pattern (o1 -> supports).
    f.preview_stored("o1", "high")
    assert f.model_id() == "o1"
    # Stored "o1" matches the model_pattern, so its capability is synthesized as supported.
    assert f.reasoning_raw() == "high"

    # Load the live catalog; now unlocked and stored model selectable.
    f.load_catalog(_catalog(), "o1", "high")
    assert f.model_id() == "o1"
    assert f.reasoning_raw() == "high"

    # Select the non-reasoning model -> raw clears.
    idx = f.model.findData("gpt-x")
    f.model.setCurrentIndex(idx)
    assert f.reasoning_raw() == ""


def test_model_reasoning_field_budget(qtbot):
    f = _ModelReasoningField("Chairman")
    qtbot.addWidget(f)
    f.configure(_budget_spec())
    f.load_catalog(
        [{"id": "claude-x", "label": "Claude X", "supports_reasoning": True}],
        "claude-x",
        "8000",
    )
    assert f.model_id() == "claude-x"
    assert f.reasoning_raw() == "8000"

    # Disable the budget knob -> raw clears.
    f._budget_enable.setChecked(False)
    assert f.reasoning_raw() == ""


def test_model_reasoning_field_none(qtbot):
    f = _ModelReasoningField("X")
    qtbot.addWidget(f)
    f.configure(_none_spec())
    f.load_catalog(_catalog(), "gpt-x", None)
    assert f.reasoning_raw() == ""
    # _refresh_reasoning early-returns for kind == none.
    f._refresh_reasoning()


def test_model_reasoning_field_preview_no_stored(qtbot):
    f = _ModelReasoningField("X")
    qtbot.addWidget(f)
    f.configure(_effort_spec())
    f.preview_stored(None, None)
    assert f.model_id() is None


# --------------------------------------------------------------------------- ProvidersPage


def _make_providers_page(qtbot) -> ProvidersPage:
    with _no_spawn():
        p = ProvidersPage()
    qtbot.addWidget(p)
    return p


def _provider_state() -> dict:
    return {
        "specs": [_effort_spec(), _budget_spec()],
        "settings": {
            "openai": {
                "has_key": True,
                "default_model": "o1",
                "reasoning": "high",
                "chairman_model": "o1",
                "chairman_reasoning": "medium",
                "is_enabled": True,
            },
            "anthropic": {
                "has_key": True,
                "default_model": "claude-x",
                "reasoning": "8000",
                "chairman_model": "claude-x",
                "chairman_reasoning": "",
                "is_enabled": False,
            },
        },
    }


@pytest.mark.asyncio
async def test_providers_page_load_and_provider_change(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()
    assert p._provider.count() == 2
    # First provider (openai, enabled) selected.
    assert p._current_spec()["key"] == "openai"
    assert p._badge.text() == "enabled"

    # Switch to anthropic (disabled but has key).
    p._provider.setCurrentIndex(1)
    assert p._current_spec()["key"] == "anthropic"
    assert p._badge.text() == "disabled"
    assert p._disable.isEnabled() is True


@pytest.mark.asyncio
async def test_providers_page_not_configured_badge(qtbot):
    state = {"specs": [_effort_spec()], "settings": {}}
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=state):
        await p._load()
    assert p._badge.text() == "not configured"
    assert p._disable.isEnabled() is False


@pytest.mark.asyncio
async def test_providers_page_key_edited_resets(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()
    p._save.setEnabled(True)
    p._on_key_edited("new-key")
    assert p._save.isEnabled() is False
    assert p._models == []


@pytest.mark.asyncio
async def test_providers_page_test_success(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()
    with patch.object(providers_mod.engine, "fetch_models", return_value=_catalog()):
        await p._do_test()
    assert p._models == _catalog()
    assert p._save.isEnabled() is True
    assert p._badge.text() == "key valid"
    assert "models loaded" in p._status.text()


@pytest.mark.asyncio
async def test_providers_page_test_empty_catalog(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()
    with patch.object(providers_mod.engine, "fetch_models", return_value=[]):
        await p._do_test()
    assert p._save.isEnabled() is False
    assert "no models" in p._status.text().lower()


@pytest.mark.asyncio
async def test_providers_page_test_error(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()

    async def _boom(*a, **k):
        raise RuntimeError("bad key\nsecond line")

    with patch.object(providers_mod.engine, "fetch_models", side_effect=_boom):
        await p._do_test()
    assert p._models == []
    assert p._save.isEnabled() is False
    assert "⚠" in p._status.text()
    assert "second line" not in p._status.text()  # _short keeps only first line


@pytest.mark.asyncio
async def test_providers_page_save_success(qtbot):
    p = _make_providers_page(qtbot)
    state = _provider_state()
    with patch.object(providers_mod.engine, "provider_state", return_value=state):
        await p._load()
        with patch.object(
            providers_mod.engine, "apply_provider", return_value=(True, None)
        ) as apply_mock:
            await p._do_save()
    apply_mock.assert_called_once()
    assert "Saved" in p._status.text()


@pytest.mark.asyncio
async def test_providers_page_save_failure(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()
        with patch.object(providers_mod.engine, "apply_provider", return_value=(False, "nope")):
            await p._do_save()
    assert "nope" in p._status.text()


@pytest.mark.asyncio
async def test_providers_page_disable(qtbot):
    p = _make_providers_page(qtbot)
    with patch.object(providers_mod.engine, "provider_state", return_value=_provider_state()):
        await p._load()
        with patch.object(providers_mod.engine, "disable_provider", return_value=True) as dis_mock:
            await p._do_disable()
    dis_mock.assert_called_once()
    assert "disabled" in p._status.text().lower()


def test_providers_page_spawn_static(qtbot):
    # Exercise the static _spawn under a patched ensure_future (no loop needed).
    with patch("asyncio.ensure_future") as ef:

        async def _c():
            return None

        ProvidersPage._spawn(_c())
    ef.assert_called_once()


# --------------------------------------------------------------------------- AgentsPage


def _agents_cfg() -> list[dict]:
    return [
        {
            "key": "chair",
            "name": "Chairman",
            "role": "chairman",
            "default_provider": "openai",
            "default_model": "gpt-x",
            "can_delete": False,
        },
        {
            "key": "strategist",
            "name": "Strategist",
            "role": "member",
            "default_provider": "openai",
            "default_model": "gpt-x",
            "can_delete": True,
        },
    ]


def _make_agents_page(qtbot) -> AgentsPage:
    # AgentsPage's module-level _spawn attaches a done-callback, so neutralise it directly.
    with patch.object(agents_mod, "_spawn", lambda coro: coro.close()):
        p = AgentsPage()
    qtbot.addWidget(p)
    return p


@pytest.mark.asyncio
async def test_agents_page_load_and_selection(qtbot):
    p = _make_agents_page(qtbot)
    with patch.object(agents_mod.engine, "list_agents_cfg", return_value=_agents_cfg()):
        await p._load()
    assert p._list.count() == 2

    # Select the chairman (cannot delete).
    p._list.setCurrentRow(0)
    assert p._selected()["key"] == "chair"
    assert p._edit.isEnabled() is True
    assert p._delete.isEnabled() is False

    # Select the strategist (deletable).
    p._list.setCurrentRow(1)
    assert p._delete.isEnabled() is True


@pytest.mark.asyncio
async def test_agents_page_open_edit_and_edit_selected(qtbot):
    p = _make_agents_page(qtbot)
    with patch.object(agents_mod.engine, "list_agents_cfg", return_value=_agents_cfg()):
        await p._load()
    p._list.setCurrentRow(1)

    with patch.object(agents_mod, "AgentEditDialog") as Dlg:
        instance = Dlg.return_value
        p._edit_selected()
        Dlg.assert_called_once()
        instance.show.assert_called_once()

    # Add (key=None) path.
    with patch.object(agents_mod, "AgentEditDialog") as Dlg:
        p._open_edit(None)
        Dlg.assert_called_once()


def test_agents_page_edit_selected_no_selection(qtbot):
    p = _make_agents_page(qtbot)
    # No agents loaded -> _selected() is None -> _edit_selected no-ops.
    p._edit_selected()  # must not raise


@pytest.mark.asyncio
async def test_agents_page_delete_confirm(qtbot):
    p = _make_agents_page(qtbot)
    with patch.object(agents_mod.engine, "list_agents_cfg", return_value=_agents_cfg()):
        await p._load()
    p._list.setCurrentRow(1)

    with patch.object(agents_mod, "QMessageBox") as Box:
        instance = Box.return_value
        p._delete_selected()
        instance.show.assert_called_once()


def test_agents_page_delete_no_selection(qtbot):
    p = _make_agents_page(qtbot)
    p._delete_selected()  # no current item -> returns silently


@pytest.mark.asyncio
async def test_agents_page_do_delete_success(qtbot):
    p = _make_agents_page(qtbot)
    with patch.object(agents_mod.engine, "list_agents_cfg", return_value=_agents_cfg()):
        await p._load()
        with patch.object(agents_mod.engine, "delete_agent", return_value=None) as del_mock:
            await p._do_delete("strategist")
    del_mock.assert_called_once_with("strategist")


@pytest.mark.asyncio
async def test_agents_page_do_delete_error(qtbot):
    p = _make_agents_page(qtbot)
    with patch.object(agents_mod.engine, "list_agents_cfg", return_value=_agents_cfg()):
        await p._load()

    async def _boom(*a, **k):
        raise RuntimeError("cannot delete")

    with patch.object(agents_mod.engine, "delete_agent", side_effect=_boom):
        await p._do_delete("strategist")
    assert "cannot delete" in p._status.text()


def test_agents_page_module_spawn(qtbot):
    # Exercise the module-level _spawn helper with ensure_future patched.
    with patch("asyncio.ensure_future") as ef:

        async def _c():
            return None

        agents_mod._spawn(_c())
    ef.assert_called_once()


# --------------------------------------------------------------------------- UpdatesPage


def test_updates_page_unsupported(qtbot):
    with _no_spawn(), patch.object(updates_mod.updater, "updates_supported", return_value=False):
        p = UpdatesPage()
    qtbot.addWidget(p)
    assert p._button.text() == "Up to date"
    assert p._button.isEnabled() is False


def test_updates_page_supported_construction(qtbot):
    with _no_spawn(), patch.object(updates_mod.updater, "updates_supported", return_value=True):
        p = UpdatesPage()
    qtbot.addWidget(p)
    assert p._button.text() == "Check for latest"
    assert p._button.isEnabled() is True


@pytest.mark.asyncio
async def test_updates_page_check_available(qtbot):
    with _no_spawn(), patch.object(updates_mod.updater, "updates_supported", return_value=True):
        p = UpdatesPage()
    qtbot.addWidget(p)
    with patch.object(updates_mod.updater, "available_update", return_value="9.9.9"):
        await p._check()
    assert p._new_version == "9.9.9"
    assert p._button.text() == "Update & restart"
    assert "9.9.9" in p._status.text()


@pytest.mark.asyncio
async def test_updates_page_check_up_to_date(qtbot):
    with _no_spawn(), patch.object(updates_mod.updater, "updates_supported", return_value=True):
        p = UpdatesPage()
    qtbot.addWidget(p)
    with patch.object(updates_mod.updater, "available_update", return_value=None):
        await p._check()
    assert p._new_version is None
    assert p._button.isEnabled() is False
    assert "latest" in p._status.text().lower()


@pytest.mark.asyncio
async def test_updates_page_apply_returns(qtbot):
    with _no_spawn(), patch.object(updates_mod.updater, "updates_supported", return_value=True):
        p = UpdatesPage()
    qtbot.addWidget(p)
    p._new_version = "9.9.9"
    # apply_update returning means the update did not proceed.
    with patch.object(updates_mod.updater, "apply_update", return_value=False):
        await p._apply()
    assert "could not be applied" in p._status.text()
    assert p._button.text() == "Update & restart"


def test_updates_page_on_click_routes(qtbot):
    with _no_spawn(), patch.object(updates_mod.updater, "updates_supported", return_value=True):
        p = UpdatesPage()
    qtbot.addWidget(p)

    # No new version -> _check is scheduled.
    with patch.object(p, "_spawn") as spawn:
        p._new_version = None
        p._on_click()
        spawn.assert_called_once()

    with patch.object(p, "_spawn") as spawn:
        p._new_version = "9.9.9"
        p._on_click()
        spawn.assert_called_once()


def test_updates_page_spawn_static(qtbot):
    with patch("asyncio.ensure_future") as ef:

        async def _c():
            return None

        UpdatesPage._spawn(_c())
    ef.assert_called_once()
