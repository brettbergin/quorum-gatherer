"""Main window: sidebar of sessions + composer + live council grid + Chairman report."""

from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from quorum_core import __version__
from quorum_desktop import engine
from quorum_desktop.bridge import CouncilBridge
from quorum_desktop.widgets.agent_chat_dialog import AgentChatDialog
from quorum_desktop.widgets.agent_panel import AgentPanel
from quorum_desktop.widgets.chairman_report import ChairmanReport
from quorum_desktop.widgets.composer import Composer
from quorum_desktop.widgets.report_dialog import ChairmanReportDialog
from quorum_desktop.widgets.settings_dialog import SettingsDialog


def _spawn(coro) -> None:
    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"quorum-gatherer — Product Strategy Council  (v{__version__})")
        self.resize(1480, 940)
        self.setMinimumSize(1100, 720)

        self._chat_id: str | None = None
        self._bridge: CouncilBridge | None = None
        self._panels: dict[str, AgentPanel] = {}
        self._chat_titles: dict[str, str] = {}
        self._session_dialog = None  # keeps the active rename/delete dialog alive
        self._settings_dialog = None  # keeps the open settings dialog alive
        self._chat_dialog = None  # the open AgentChatDialog (if any)
        self._chat_dialog_key: str | None = None  # which agent it's showing
        self._running_agents: set[str] = set()  # agents currently streaming a deliberation

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main(), 1)
        self.setCentralWidget(root)

        # Defer the first async work to the first event-loop tick: creating a Task in __init__
        # (before qasync's loop is the running loop) trips Python 3.14's stricter asyncio checks.
        QTimer.singleShot(0, lambda: _spawn(self._startup()))

    # ----------------------------------------------------------------- sidebar
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setFixedWidth(240)
        v = QVBoxLayout(side)
        brand = QLabel("⚖️  quorum-gatherer")
        brand.setStyleSheet("font-weight:700; font-size:15px;")
        v.addWidget(brand)

        new_btn = QPushButton("+ New Council")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(lambda: _spawn(self._new_session()))
        v.addWidget(new_btn)

        self._chat_list = QListWidget()
        self._chat_list.itemClicked.connect(
            lambda item: _spawn(self._select_chat(item.data(Qt.ItemDataRole.UserRole)))
        )
        # Rename on double-click; right-click for a Rename/Delete menu.
        self._chat_list.itemDoubleClicked.connect(
            lambda item: self._prompt_rename(item.data(Qt.ItemDataRole.UserRole))
        )
        self._chat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._chat_list.customContextMenuRequested.connect(self._on_chat_context_menu)
        v.addWidget(self._chat_list, 1)

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.clicked.connect(self._open_settings)
        v.addWidget(settings_btn)
        return side

    # ----------------------------------------------------------------- main
    def _build_main(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        v = QVBoxLayout(container)

        header = QHBoxLayout()
        self._title = QLabel("Council session")
        self._title.setStyleSheet("font-size:20px; font-weight:700;")
        self._phase = QLabel("")
        self._phase.setObjectName("muted")
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._phase)
        v.addLayout(header)

        self._composer = Composer()
        self._composer.submit.connect(lambda idea: _spawn(self._on_submit(idea)))
        self._composer.upload.connect(lambda path: _spawn(self._on_upload(path)))
        v.addWidget(self._composer)

        grid_wrap = QWidget()
        self._grid = QGridLayout(grid_wrap)
        v.addWidget(grid_wrap)  # populated by _rebuild_grid() once agents are loaded from the DB

        self._report = ChairmanReport()
        self._report.expand_requested.connect(self._open_report)
        self._report.convene_requested.connect(lambda: _spawn(self._on_convene_chairman()))
        v.addWidget(self._report)
        v.addStretch(1)

        scroll.setWidget(container)
        return scroll

    def _rebuild_grid(self) -> None:
        """(Re)build the agent panel grid from the current roster. Called after the agents are
        loaded/seeded and whenever the roster changes, so new agents appear without a restart."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._panels = {}
        for i, member in enumerate(engine.registry().members):
            panel = AgentPanel(member.name, member.key)
            panel.details_requested.connect(lambda key: _spawn(self._open_agent_chat(key)))
            panel.active_toggled.connect(self._on_agent_toggled)
            self._panels[member.key] = panel
            self._grid.addWidget(panel, i // 3, i % 3)

    # ----------------------------------------------------------------- controller
    async def _startup(self) -> None:
        await engine.ensure_agents()  # first-boot ETL of prompts into the DB; build registry
        self._rebuild_grid()
        chats = await engine.list_chats()
        if not chats:
            cid = await engine.create_chat("New council session", None)
            chats = await engine.list_chats()
        else:
            cid = chats[0]["id"]
        self._refresh_chat_list(chats)
        await self._select_chat(cid)

    def _refresh_chat_list(self, chats: list[dict]) -> None:
        self._chat_titles = {c["id"]: (c["title"] or "") for c in chats}
        self._chat_list.clear()
        for c in chats:
            item = QListWidgetItem(f"{c['title'] or 'Untitled'}\n{c['status']}")
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            self._chat_list.addItem(item)
            if c["id"] == self._chat_id:
                self._chat_list.setCurrentItem(item)

    async def _new_session(self) -> None:
        cid = await engine.create_chat("New council session", None)
        self._refresh_chat_list(await engine.list_chats())
        await self._select_chat(cid)

    # ----------------------------------------------------------------- rename / delete
    # Modal dialogs (menu.exec / QInputDialog / QMessageBox) run a NESTED Qt event loop, during
    # which qasync does not drive asyncio. So all prompting happens in these synchronous slots; only
    # the DB work is spawned afterwards, as a clean task with no nested loop inside it.
    def _on_chat_context_menu(self, pos) -> None:
        item = self._chat_list.itemAt(pos)
        if item is None:
            return
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self._chat_list)
        rename_action = menu.addAction("Rename…")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._chat_list.mapToGlobal(pos))
        if chosen == rename_action:
            self._prompt_rename(chat_id)
        elif chosen == delete_action:
            self._confirm_delete(chat_id)

    def _prompt_rename(self, chat_id: str) -> None:
        # Non-blocking dialog (show, not exec): a task spawned right after a modal's nested event
        # loop collapses is never driven by qasync, so we trigger the async work from a signal
        # that fires on a clean outer-loop tick instead.
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Rename session")
        dlg.setLabelText("Session name:")
        dlg.setTextValue(self._chat_titles.get(chat_id, ""))
        dlg.setModal(True)
        dlg.textValueSelected.connect(lambda text: _spawn(self._do_rename(chat_id, text)))
        dlg.finished.connect(lambda _r: dlg.deleteLater())
        self._session_dialog = dlg
        dlg.show()

    def _confirm_delete(self, chat_id: str) -> None:
        name = self._chat_titles.get(chat_id) or "this session"
        box = QMessageBox(self)
        box.setWindowTitle("Delete session")
        box.setText(f"Delete “{name}”? This permanently removes its deliberations and report.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setModal(True)

        def _on_click(btn) -> None:
            if box.standardButton(btn) == QMessageBox.StandardButton.Yes:
                _spawn(self._do_delete(chat_id))

        box.buttonClicked.connect(_on_click)
        box.finished.connect(lambda _r: box.deleteLater())
        self._session_dialog = box
        box.show()

    async def _do_rename(self, chat_id: str, title: str) -> None:
        await engine.rename_chat(chat_id, title)
        self._refresh_chat_list(await engine.list_chats())
        if chat_id == self._chat_id:
            self._title.setText(title.strip() or "Council session")

    async def _do_delete(self, chat_id: str) -> None:
        await engine.delete_chat(chat_id)
        chats = await engine.list_chats()
        if not chats:
            await self._new_session()
            return
        # If the active session was deleted, switch to another one first.
        if chat_id == self._chat_id:
            await self._select_chat(chats[0]["id"])
        # Always rebuild the sidebar so the deleted row disappears (and the current row highlights).
        self._refresh_chat_list(chats)

    async def _select_chat(self, chat_id: str) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        self._chat_id = chat_id
        self._phase.setText("")
        self._composer.set_running(False)
        d = await engine.get_chat(chat_id)
        if d is None:
            return
        self._title.setText(d["title"] or "Council session")
        self._composer.set_idea(d["idea"] or "")
        self._composer.set_documents([doc["filename"] for doc in d["documents"]])
        runs = {r["agent_key"]: r for r in d["runs"]}
        active = d.get("active_agents")  # None = all members active
        for key, panel in self._panels.items():
            panel.set_active(active is None or key in active)
            r = runs.get(key)
            if r:
                panel.hydrate(r["status"], r["output_text"], r["provider"], r["model"], r["error"])
                panel.set_chatted(bool(r.get("chatted")))
            else:
                panel.reset()
        if d["report_markdown"]:
            self._report.set_markdown(d["report_markdown"])
        else:
            self._report.reset()
        # The Chairman can be convened once deliberation has produced contributions.
        self._report.set_convene_enabled(d["status"] in ("deliberated", "completed"))

    async def _on_upload(self, path: str) -> None:
        if not self._chat_id:
            return
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        await engine.add_document(self._chat_id, Path(path).name, text)
        d = await engine.get_chat(self._chat_id)
        self._composer.set_documents([doc["filename"] for doc in d["documents"]])

    def _start_bridge(self) -> CouncilBridge:
        """Subscribe a fresh bridge to the chat's event stream and wire the live-view slots."""
        if self._bridge is not None:
            self._bridge.stop()
        bridge = CouncilBridge(self._chat_id)
        bridge.agent_started.connect(self._on_started)
        bridge.agent_token.connect(self._on_token)
        bridge.agent_complete.connect(self._on_complete)
        bridge.agent_failed.connect(self._on_failed)
        bridge.phase_changed.connect(self._on_phase)
        bridge.council_report.connect(self._on_report)
        bridge.deliberation_complete.connect(self._on_deliberation_complete)
        bridge.error.connect(self._on_error)
        bridge.finished.connect(lambda: _spawn(self._on_finished()))
        bridge.start()
        self._bridge = bridge
        return bridge

    async def _on_submit(self, idea: str) -> None:
        if not self._chat_id:
            return
        await engine.set_idea(self._chat_id, idea)
        # reset live view
        for panel in self._panels.values():
            panel.reset()
        self._report.reset()
        self._phase.setText("deliberation")
        self._composer.set_running(True)
        self._report.set_convene_enabled(False)
        self._start_bridge()
        _spawn(engine.run_deliberation(self._chat_id))

    async def _on_convene_chairman(self) -> None:
        if not self._chat_id:
            return
        self._report.set_convene_enabled(False)
        self._report.set_synthesizing(True)
        self._phase.setText("synthesis")
        self._start_bridge()
        _spawn(engine.run_synthesis(self._chat_id))

    # ----------------------------------------------------------------- bridge slots
    def _live_dialog_for(self, key: str):
        """The open chat dialog if it's showing this agent (for live token forwarding)."""
        if self._chat_dialog is not None and self._chat_dialog_key == key:
            return self._chat_dialog
        return None

    def _on_started(self, key: str, provider: str, model: str) -> None:
        self._running_agents.add(key)
        if key in self._panels:
            self._panels[key].set_started(provider, model)
        dlg = self._live_dialog_for(key)
        if dlg is not None:
            dlg.begin_live()

    def _on_token(self, key: str, delta: str) -> None:
        if key in self._panels:
            self._panels[key].append_token(delta)
        dlg = self._live_dialog_for(key)
        if dlg is not None:
            dlg.append_live(delta)

    def _on_complete(self, key: str, text: str) -> None:
        self._running_agents.discard(key)
        if key in self._panels:
            self._panels[key].set_complete(text)
        dlg = self._live_dialog_for(key)
        if dlg is not None:
            dlg.end_live(text)

    def _on_failed(self, key: str, error: str) -> None:
        self._running_agents.discard(key)
        if key in self._panels:
            self._panels[key].set_failed(error)
        dlg = self._live_dialog_for(key)
        if dlg is not None:
            dlg.end_live(f"⚠ {error}")

    def _on_phase(self, phase: str) -> None:
        self._phase.setText(phase)
        if phase == "synthesis":
            self._report.set_synthesizing(True)

    def _on_report(self, markdown: str, _content: dict) -> None:
        self._report.set_markdown(markdown)

    def _on_deliberation_complete(self) -> None:
        self._phase.setText("awaiting Chairman")
        self._report.set_convene_enabled(True)

    def _on_agent_toggled(self, _key: str, _on: bool) -> None:
        # Persist the current set of checked members for this chat (per-session activation).
        if not self._chat_id:
            return
        active = [k for k, p in self._panels.items() if p.is_active()]
        _spawn(engine.set_active_agents(self._chat_id, active))

    def _on_error(self, message: str) -> None:
        self._report.set_markdown(f"**Error:** {message}")

    async def _on_finished(self) -> None:
        self._composer.set_running(False)
        self._refresh_chat_list(await engine.list_chats())

    def _open_report(self, markdown: str) -> None:
        if markdown.strip():
            ChairmanReportDialog(self, markdown).exec()

    async def _open_agent_chat(self, agent_key: str) -> None:
        if not self._chat_id:
            return
        member = next((m for m in engine.registry().members if m.key == agent_key), None)
        # Fetch the conversation on the live loop, then render synchronously — qasync does not
        # pump asyncio inside a modal exec()'s nested loop, so we must not load there.
        data = await engine.agent_conversation(self._chat_id, agent_key)
        if data is None:
            data = {"agent_name": member.name if member else agent_key, "turns": []}
        dialog = AgentChatDialog(self, self._chat_id, agent_key, data)
        # Modal to the window but NON-blocking (show, not exec) so streamed replies keep running.
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        def _on_closed(_r) -> None:
            if self._chat_dialog is dialog:
                self._chat_dialog = None
                self._chat_dialog_key = None
            _spawn(self._select_chat(self._chat_id))

        dialog.finished.connect(_on_closed)
        self._chat_dialog = dialog  # keep a reference so it isn't garbage-collected
        self._chat_dialog_key = agent_key
        dialog.show()
        # If this agent is mid-deliberation, seed + stream its in-progress response live.
        if agent_key in self._running_agents:
            panel = self._panels.get(agent_key)
            dialog.begin_live(panel.current_text() if panel else "")

    def _open_settings(self) -> None:
        # Non-blocking (show, not exec): the Providers/Agents pages do async DB work, which qasync
        # cannot drive inside a modal exec()'s nested loop.
        dialog = SettingsDialog(self)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        def _on_closed(_r) -> None:
            # Roster may have changed — rebuild the grid and re-sync the current chat.
            self._rebuild_grid()
            if self._chat_id:
                _spawn(self._select_chat(self._chat_id))

        dialog.finished.connect(_on_closed)
        self._settings_dialog = dialog  # keep alive
        dialog.show()
