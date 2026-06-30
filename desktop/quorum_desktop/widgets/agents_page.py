"""Settings page: manage the council roster — add, edit (prompt + frontmatter), reset, delete."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quorum_desktop import engine
from quorum_desktop.widgets.agent_edit_dialog import AgentEditDialog


def _spawn(coro) -> None:
    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


class AgentsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._dialog: QWidget | None = None  # keeps the open edit/confirm dialog alive

        outer = QVBoxLayout(self)
        title = QLabel("Agents")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        outer.addWidget(title)
        blurb = QLabel(
            "The council roster. Edit an agent's prompt and settings, add new members, or reset a "
            "shipped agent to its original prompt. Changes take effect on the next deliberation."
        )
        blurb.setObjectName("muted")
        blurb.setWordWrap(True)
        outer.addWidget(blurb)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(
            lambda item: self._open_edit(item.data(Qt.ItemDataRole.UserRole))
        )
        self._list.currentRowChanged.connect(self._on_selection)
        outer.addWidget(self._list, 1)

        row = QHBoxLayout()
        add = QPushButton("+ Add agent")
        add.setObjectName("primary")
        add.clicked.connect(lambda: self._open_edit(None))
        self._edit = QPushButton("Edit")
        self._edit.clicked.connect(self._edit_selected)
        self._delete = QPushButton("Delete")
        self._delete.clicked.connect(self._delete_selected)
        row.addWidget(add)
        row.addStretch(1)
        row.addWidget(self._edit)
        row.addWidget(self._delete)
        outer.addLayout(row)

        self._status = QLabel("")
        self._status.setObjectName("statusLine")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        self._agents: list[dict] = []
        _spawn(self._load())

    async def _load(self) -> None:
        self._agents = await engine.list_agents_cfg()
        self._list.clear()
        for a in self._agents:
            tag = "  ·  chairman" if a["role"] == "chairman" else ""
            meta = f"{a['default_provider']} · {a['default_model']}"
            item = QListWidgetItem(f"{a['name']}{tag}\n{meta}")
            item.setData(Qt.ItemDataRole.UserRole, a["key"])
            self._list.addItem(item)
        self._on_selection(self._list.currentRow())

    def _selected(self) -> dict | None:
        item = self._list.currentItem()
        if item is None:
            return None
        key = item.data(Qt.ItemDataRole.UserRole)
        return next((a for a in self._agents if a["key"] == key), None)

    def _on_selection(self, _row: int) -> None:
        agent = self._selected()
        self._edit.setEnabled(agent is not None)
        self._delete.setEnabled(bool(agent and agent.get("can_delete")))

    def _edit_selected(self) -> None:
        agent = self._selected()
        if agent:
            self._open_edit(agent["key"])

    def _open_edit(self, key: str | None) -> None:
        data = next((a for a in self._agents if a["key"] == key), None) if key else None
        dialog = AgentEditDialog(self, data)
        dialog.saved.connect(lambda: _spawn(self._load()))
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._dialog = dialog  # keep alive
        dialog.show()

    def _delete_selected(self) -> None:
        agent = self._selected()
        if not agent:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Delete agent")
        box.setText(f"Delete “{agent['name']}”? This removes its prompt and settings.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setModal(True)

        def _on_click(btn) -> None:
            if box.standardButton(btn) == QMessageBox.StandardButton.Yes:
                _spawn(self._do_delete(agent["key"]))

        box.buttonClicked.connect(_on_click)
        box.finished.connect(lambda _r: box.deleteLater())
        self._dialog = box
        box.show()

    async def _do_delete(self, key: str) -> None:
        try:
            await engine.delete_agent(key)
        except Exception as exc:  # noqa: BLE001
            self._status.setText(f"⚠ {exc}")
            self._status.setProperty("state", "error")
            self._status.style().unpolish(self._status)
            self._status.style().polish(self._status)
            return
        await self._load()
