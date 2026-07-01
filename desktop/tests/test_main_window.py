"""Headless coverage for the desktop MainWindow, theme, and app bootstrap helpers.

Everything runs under the offscreen Qt platform (set in conftest). Anything that needs a
live qasync loop, a modal exec(), or the network is patched out: the module-level `_spawn`
is replaced with a synchronous coroutine driver, dialog classes are stubbed/`show`-only,
and engine I/O hits the seeded temp SQLite DB from the `db` fixture.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from quorum_desktop import app as app_module
from quorum_desktop import engine, theme
from quorum_desktop.windows import main_window as mw_module
from quorum_desktop.windows.main_window import MainWindow, _spawn


def _drain(coro) -> None:
    """Stand in for `_spawn` (fire-and-forget). Inside an already-running loop (async tests)
    schedule the coroutine; otherwise run it to completion on a fresh loop (sync tests)."""
    if not asyncio.iscoroutine(coro):
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.new_event_loop().run_until_complete(coro)
    else:
        asyncio.ensure_future(coro)


@pytest.fixture
def spawn_sync(monkeypatch):
    """Make the window's fire-and-forget `_spawn` run coroutines synchronously."""
    monkeypatch.setattr(mw_module, "_spawn", _drain)
    return _drain


@pytest.fixture
def window(qtbot, db, spawn_sync):
    """A MainWindow with its grid populated from the seeded DB roster.

    `QTimer.singleShot` is patched so the deferred `_startup` never auto-fires; tests drive
    `_startup` (or `_rebuild_grid`) explicitly to keep everything deterministic.
    """
    with patch.object(mw_module.QTimer, "singleShot", lambda *_a, **_k: None):
        w = MainWindow()
    qtbot.addWidget(w)
    w._rebuild_grid()
    return w


# --------------------------------------------------------------------- theme + module-level


def test_apply_theme_sets_stylesheet():
    appi = QApplication.instance()
    theme.apply_theme(appi)
    assert appi.styleSheet() == theme.DARK_QSS
    assert "QPushButton#primary" in theme.DARK_QSS


def test_module_spawn_handles_completed_coro():
    async def _noop():
        return 1

    # Exercise the real _spawn + its done-callback without a window.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        _spawn(_noop())
        loop.run_until_complete(asyncio.sleep(0))
    finally:
        asyncio.set_event_loop(None)
        loop.close()


# --------------------------------------------------------------------- construction + grid


def test_window_constructs_and_builds_grid(window):
    assert window.windowTitle().startswith("quorum-gatherer")
    assert len(window._panels) == len(engine.registry().members)
    # Idempotent rebuild clears and repopulates.
    window._rebuild_grid()
    assert len(window._panels) == len(engine.registry().members)


@pytest.mark.asyncio
async def test_startup_creates_and_selects_chat(qtbot, db, spawn_sync):
    with patch.object(mw_module.QTimer, "singleShot", lambda *_a, **_k: None):
        w = MainWindow()
    qtbot.addWidget(w)
    await w._startup()
    assert w._chat_id is not None
    assert w._chat_list.count() >= 1


# --------------------------------------------------------------------- chat list / selection


@pytest.mark.asyncio
async def test_new_session_and_select(window):
    cid = await engine.create_chat("Test session", "an idea")
    await window._select_chat(cid)
    assert window._chat_id == cid
    assert window._title.text() == "Test session"

    await window._new_session()
    assert window._chat_id is not None
    assert window._chat_list.count() >= 2


@pytest.mark.asyncio
async def test_select_missing_chat_returns_early(window):
    await window._select_chat("does-not-exist")
    # No crash; chat_id is set but title untouched beyond default flow.
    assert window._chat_id == "does-not-exist"


def test_refresh_chat_list_marks_current(window):
    window._chat_id = "c1"
    chats = [
        {"id": "c1", "title": "Alpha", "status": "created", "idea": None},
        {"id": "c2", "title": None, "status": "completed", "idea": None},
    ]
    window._refresh_chat_list(chats)
    assert window._chat_list.count() == 2
    assert window._chat_titles == {"c1": "Alpha", "c2": ""}
    assert window._chat_list.currentItem().data(Qt.ItemDataRole.UserRole) == "c1"


# --------------------------------------------------------------------- rename / delete


@pytest.mark.asyncio
async def test_do_rename_updates_title(window):
    cid = await engine.create_chat("Before", None)
    await window._select_chat(cid)
    await window._do_rename(cid, "After")
    assert window._title.text() == "After"


@pytest.mark.asyncio
async def test_do_delete_active_switches(window):
    a = await engine.create_chat("A", None)
    b = await engine.create_chat("B", None)
    await window._select_chat(a)
    await window._do_delete(a)
    # Active chat was deleted -> switched to a surviving one.
    assert window._chat_id != a
    assert window._chat_id is not None
    assert (
        b
        in {
            window._chat_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(window._chat_list.count())
        }
        or window._chat_id == b
    )


@pytest.mark.asyncio
async def test_do_delete_last_creates_new(window, monkeypatch):
    # Delete everything, then deleting the final chat triggers _new_session.
    for c in await engine.list_chats():
        await engine.delete_chat(c["id"])
    cid = await engine.create_chat("Solo", None)
    await window._select_chat(cid)
    await window._do_delete(cid)
    assert window._chat_id is not None
    assert window._chat_id != cid


def test_prompt_rename_shows_dialog(window, monkeypatch):
    shown = {}
    monkeypatch.setattr(mw_module.QInputDialog, "show", lambda self: shown.setdefault("ok", True))
    window._chat_titles = {"c1": "Name"}
    window._prompt_rename("c1")
    assert shown.get("ok")
    assert window._session_dialog is not None


def test_confirm_delete_shows_box_and_yes_spawns(window, monkeypatch):
    monkeypatch.setattr(mw_module.QMessageBox, "show", lambda self: None)
    called = {}
    monkeypatch.setattr(
        mw_module, "_spawn", lambda coro: called.setdefault("c", coro) or _drain(coro)
    )
    window._chat_titles = {"c1": "Doomed"}
    window._confirm_delete("c1")
    box = window._session_dialog
    assert box is not None
    # Simulate clicking "Yes".
    yes = box.button(mw_module.QMessageBox.StandardButton.Yes)
    box.buttonClicked.emit(yes)
    assert "c" in called


def test_on_chat_context_menu_no_item(window):
    # itemAt on an empty point -> None -> early return, no crash.
    window._on_chat_context_menu(window._chat_list.rect().bottomRight())


class _FakeMenu:
    """Stand-in for QMenu. The real menu.exec() opens a modal that blocks forever headlessly,
    and PySide6 ignores a monkeypatched QMenu.exec, so swap the whole class for these tests.
    Actions are opaque objects, matching how the handler compares `chosen` by identity."""

    choice = 0  # index of the action exec() returns

    def __init__(self, parent=None):
        self._actions = []

    def addAction(self, text):
        action = object()
        self._actions.append(action)
        return action

    def exec(self, *args):
        return self._actions[type(self).choice]


def test_on_chat_context_menu_rename(window, monkeypatch):
    chats = [{"id": "c1", "title": "Alpha", "status": "created", "idea": None}]
    window._refresh_chat_list(chats)
    _FakeMenu.choice = 0  # "Rename…"
    monkeypatch.setattr(mw_module, "QMenu", _FakeMenu)
    called = {}
    monkeypatch.setattr(window, "_prompt_rename", lambda cid: called.setdefault("r", cid))
    item = window._chat_list.item(0)
    window._on_chat_context_menu(window._chat_list.visualItemRect(item).center())
    assert called.get("r") == "c1"


def test_on_chat_context_menu_delete(window, monkeypatch):
    chats = [{"id": "c1", "title": "Alpha", "status": "created", "idea": None}]
    window._refresh_chat_list(chats)
    _FakeMenu.choice = 1  # "Delete"
    monkeypatch.setattr(mw_module, "QMenu", _FakeMenu)
    called = {}
    monkeypatch.setattr(window, "_confirm_delete", lambda cid: called.setdefault("d", cid))
    item = window._chat_list.item(0)
    window._on_chat_context_menu(window._chat_list.visualItemRect(item).center())
    assert called.get("d") == "c1"


# --------------------------------------------------------------------- upload / submit / convene


@pytest.mark.asyncio
async def test_on_upload(window, tmp_path):
    cid = await engine.create_chat("Up", None)
    await window._select_chat(cid)
    f = tmp_path / "doc.txt"
    f.write_text("hello context", encoding="utf-8")
    await window._on_upload(str(f))
    d = await engine.get_chat(cid)
    assert any(doc["filename"] == "doc.txt" for doc in d["documents"])


@pytest.mark.asyncio
async def test_on_upload_no_chat_returns(window):
    window._chat_id = None
    await window._on_upload("/nonexistent")  # early return


@pytest.mark.asyncio
async def test_on_submit_starts_bridge(window, monkeypatch):
    cid = await engine.create_chat("Submit", None)
    await window._select_chat(cid)
    monkeypatch.setattr(window, "_start_bridge", MagicMock())
    monkeypatch.setattr(engine, "run_deliberation", lambda _c: asyncio.sleep(0))
    await window._on_submit("Build a widget")
    window._start_bridge.assert_called_once()
    assert window._phase.text() == "deliberation"


@pytest.mark.asyncio
async def test_on_submit_no_chat(window):
    window._chat_id = None
    await window._on_submit("idea")  # early return


@pytest.mark.asyncio
async def test_on_convene_chairman(window, monkeypatch):
    cid = await engine.create_chat("Convene", None)
    await window._select_chat(cid)
    monkeypatch.setattr(window, "_start_bridge", MagicMock())
    monkeypatch.setattr(engine, "run_synthesis", lambda _c: asyncio.sleep(0))
    await window._on_convene_chairman()
    window._start_bridge.assert_called_once()
    assert window._phase.text() == "synthesis"


@pytest.mark.asyncio
async def test_on_convene_no_chat(window):
    window._chat_id = None
    await window._on_convene_chairman()


# --------------------------------------------------------------------- bridge wiring + slots


def test_start_bridge_requires_chat(window):
    window._chat_id = None
    with pytest.raises(RuntimeError):
        window._start_bridge()


def test_start_bridge_replaces_existing(window, monkeypatch):
    window._chat_id = "c1"
    fake_bridges = []

    class FakeBridge:
        def __init__(self, chat_id):
            self.chat_id = chat_id
            self.started = False
            self.stopped = False
            for sig in (
                "agent_started",
                "agent_token",
                "agent_complete",
                "agent_failed",
                "phase_changed",
                "council_report",
                "deliberation_complete",
                "error",
                "finished",
            ):
                setattr(self, sig, MagicMock())
            fake_bridges.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(mw_module, "CouncilBridge", FakeBridge)
    b1 = window._start_bridge()
    assert b1.started
    b2 = window._start_bridge()
    assert b1.stopped  # old one stopped when a new bridge starts
    assert b2 is window._bridge


def _key(window):
    return next(iter(window._panels))


def test_bridge_slots_drive_panels(window):
    key = _key(window)
    window._on_started(key, "openai", "gpt-x")
    assert key in window._running_agents
    window._on_token(key, "abc")
    window._on_complete(key, "done")
    assert key not in window._running_agents
    window._on_started(key, "p", "m")
    window._on_failed(key, "boom")
    assert key not in window._running_agents
    # Unknown keys are tolerated.
    window._on_started("ghost", "p", "m")
    window._on_token("ghost", "x")
    window._on_complete("ghost", "y")
    window._on_failed("ghost", "z")


def test_phase_and_report_slots(window):
    window._on_phase("deliberation")
    assert window._phase.text() == "deliberation"
    window._on_phase("synthesis")  # also flips report into synthesizing
    window._on_report("# Title", {})
    window._on_deliberation_complete()
    assert window._phase.text() == "awaiting Chairman"
    window._on_error("kaboom")


def test_bridge_slots_forward_to_live_dialog(window):
    key = _key(window)
    dlg = MagicMock()
    window._chat_dialog = dlg
    window._chat_dialog_key = key
    assert window._live_dialog_for(key) is dlg
    assert window._live_dialog_for("other") is None
    window._on_started(key, "p", "m")
    dlg.begin_live.assert_called_once()
    window._on_token(key, "d")
    dlg.append_live.assert_called_with("d")
    window._on_complete(key, "final")
    dlg.end_live.assert_called_with("final")
    # Failed path with a live dialog.
    window._chat_dialog = dlg
    window._chat_dialog_key = key
    window._on_started(key, "p", "m")
    window._on_failed(key, "err")


@pytest.mark.asyncio
async def test_on_finished(window):
    cid = await engine.create_chat("Fin", None)
    await window._select_chat(cid)
    await window._on_finished()
    assert window._composer._convene.text() == "Begin deliberation"  # set_running(False) reset


def test_on_agent_toggled_persists(window, monkeypatch):
    window._chat_id = "c1"
    captured = {}
    monkeypatch.setattr(mw_module, "_spawn", lambda coro: captured.setdefault("c", coro))
    monkeypatch.setattr(engine, "set_active_agents", lambda *a: asyncio.sleep(0))
    window._on_agent_toggled("k", True)
    assert "c" in captured
    # Close the captured coroutine to avoid a "never awaited" warning.
    captured["c"].close()


def test_on_agent_toggled_no_chat(window):
    window._chat_id = None
    window._on_agent_toggled("k", True)  # early return


# --------------------------------------------------------------------- report / dialogs


def test_open_report_with_text(window, monkeypatch):
    called = {}

    class FakeDialog:
        def __init__(self, parent, markdown):
            called["md"] = markdown

        def exec(self):
            called["exec"] = True

    monkeypatch.setattr(mw_module, "ChairmanReportDialog", FakeDialog)
    window._open_report("# Real content")
    assert called.get("exec")
    assert called["md"] == "# Real content"


def test_open_report_blank_noop(window, monkeypatch):
    monkeypatch.setattr(
        mw_module, "ChairmanReportDialog", MagicMock(side_effect=AssertionError("should not open"))
    )
    window._open_report("   ")  # blank -> no dialog


@pytest.mark.asyncio
async def test_open_agent_chat(window, monkeypatch):
    cid = await engine.create_chat("Chat", "an idea")
    await window._select_chat(cid)
    key = _key(window)

    class FakeChatDialog:
        def __init__(self, parent, chat_id, agent_key, data):
            self.agent_key = agent_key
            self.data = data
            self._finished_cb = None

        def setWindowModality(self, _m):
            pass

        @property
        def finished(self):
            owner = self

            class _Sig:
                def connect(self, cb):
                    owner._finished_cb = cb

            return _Sig()

        def show(self):
            self.shown = True

        def begin_live(self, initial=""):
            self.live = initial

    monkeypatch.setattr(mw_module, "AgentChatDialog", FakeChatDialog)
    await window._open_agent_chat(key)
    assert window._chat_dialog is not None
    assert window._chat_dialog_key == key

    # Running-agent path seeds live streaming from the panel.
    window._running_agents.add(key)
    await window._open_agent_chat(key)
    assert hasattr(window._chat_dialog, "live")


@pytest.mark.asyncio
async def test_open_agent_chat_no_chat(window):
    window._chat_id = None
    await window._open_agent_chat("k")  # early return


def test_open_settings(window, monkeypatch):
    instances = []

    class FakeSettings:
        def __init__(self, parent=None):
            self._cb = None
            instances.append(self)

        def setWindowModality(self, _m):
            pass

        @property
        def finished(self):
            owner = self

            class _Sig:
                def connect(self, cb):
                    owner._cb = cb

            return _Sig()

        def show(self):
            self.shown = True

    monkeypatch.setattr(mw_module, "SettingsDialog", FakeSettings)
    window._chat_id = None
    window._open_settings()
    dlg = window._settings_dialog
    assert dlg is not None
    # Fire the close callback (no active chat path).
    dlg._cb(0)


# --------------------------------------------------------------------- app.py bootstrap


def test_bootstrap_env_sets_defaults(monkeypatch):
    monkeypatch.delenv("QUORUM_DATABASE_URL", raising=False)
    monkeypatch.delenv("QUORUM_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr("quorum_desktop.paths.database_url", lambda: "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr("quorum_desktop.paths.ensure_encryption_key", lambda: "k" * 32)
    app_module._bootstrap_env()
    import os

    assert os.environ["QUORUM_DATABASE_URL"]
    assert os.environ["QUORUM_ENCRYPTION_KEY"]


def test_selftest_ok(monkeypatch):
    monkeypatch.setattr("quorum_core.migrate.upgrade_to_head", lambda: None)

    async def fake_create_chat(title, idea, docs):
        return "cid"

    async def fake_run(cid):
        return None

    async def fake_get_chat(cid):
        return {"report_markdown": "# R", "runs": [object()] * 8}

    monkeypatch.setattr(engine, "create_chat", fake_create_chat)
    monkeypatch.setattr(engine, "run", fake_run)
    monkeypatch.setattr(engine, "get_chat", fake_get_chat)
    assert app_module._selftest() == 0


def test_selftest_fail(monkeypatch):
    monkeypatch.setattr("quorum_core.migrate.upgrade_to_head", lambda: None)

    async def fake_create_chat(title, idea, docs):
        return "cid"

    async def fake_run(cid):
        return None

    async def fake_get_chat(cid):
        return {"report_markdown": "", "runs": []}

    monkeypatch.setattr(engine, "create_chat", fake_create_chat)
    monkeypatch.setattr(engine, "run", fake_run)
    monkeypatch.setattr(engine, "get_chat", fake_get_chat)
    assert app_module._selftest() == 1


def test_main_dispatches_to_selftest(monkeypatch):
    monkeypatch.setattr(app_module.sys, "argv", ["prog", "--selftest"])
    monkeypatch.setattr(app_module, "_selftest", lambda: 7)
    assert app_module.main() == 7
