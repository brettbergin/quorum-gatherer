"""Create or edit a council agent: frontmatter form + prompt editor + a live diff of changes.

Non-blocking (show() + signals), per this app's qasync rule. Emits `saved` after a successful
create/update/reset so the Agents page can refresh.
"""

from __future__ import annotations

import asyncio
import difflib
import html

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
)

from quorum_desktop import engine


def _spawn(coro) -> None:
    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


def _diff_html(old: str, new: str) -> str:
    if old == new:
        return "<i style='color:#8b93a3'>No changes.</i>"
    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(), lineterm="", fromfile="current", tofile="edited"
    )
    out = []
    for ln in lines:
        esc = html.escape(ln)
        if ln.startswith("+") and not ln.startswith("+++"):
            out.append(f"<span style='color:#46c66b'>{esc}</span>")
        elif ln.startswith("-") and not ln.startswith("---"):
            out.append(f"<span style='color:#e5675f'>{esc}</span>")
        elif ln.startswith("@@"):
            out.append(f"<span style='color:#5b8def'>{esc}</span>")
        else:
            out.append(f"<span style='color:#8b93a3'>{esc}</span>")
    return "<pre style='white-space:pre-wrap; margin:0'>" + "\n".join(out) + "</pre>"


class AgentEditDialog(QDialog):
    saved = Signal()

    def __init__(self, parent, data: dict | None) -> None:
        super().__init__(parent)
        self._data = data or {}
        self._key = self._data.get("key")  # None = creating a new agent
        self._creating = self._key is None
        self._original_prompt = self._data.get("system_prompt", "")
        self.setWindowTitle("Add agent" if self._creating else f"Edit — {self._data.get('name')}")
        self.setMinimumSize(QSize(720, 600))
        self.resize(1060, 880)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        if self._creating:
            self._key_edit = QLineEdit()
            self._key_edit.setPlaceholderText("lowercase_key (letters, digits, underscores)")
            form.addRow("Key", self._key_edit)
        self._name = QLineEdit(self._data.get("name", ""))
        self._provider = QLineEdit(self._data.get("default_provider", "anthropic"))
        self._model = QLineEdit(self._data.get("default_model", "claude-sonnet-4-6"))
        self._temp = QDoubleSpinBox()
        self._temp.setRange(0.0, 2.0)
        self._temp.setSingleStep(0.1)
        self._temp.setValue(float(self._data.get("temperature", 0.3)))
        self._order = QSpinBox()
        self._order.setRange(0, 999)
        self._order.setValue(int(self._data.get("display_order", 100)))
        self._sections = QLineEdit(", ".join(self._data.get("owned_sections", [])))
        self._sections.setPlaceholderText("comma-separated section keys (optional)")
        form.addRow("Name", self._name)
        form.addRow("Provider", self._provider)
        form.addRow("Model", self._model)
        form.addRow("Temperature", self._temp)
        form.addRow("Order", self._order)
        form.addRow("Owned sections", self._sections)
        if not self._creating:
            role = self._data.get("role", "council_member")
            form.addRow("Role", QLabel(role + (" (protected)" if role == "chairman" else "")))
        layout.addLayout(form)

        layout.addWidget(QLabel("Prompt"))
        self._prompt = QPlainTextEdit(self._original_prompt)
        self._prompt.textChanged.connect(self._refresh_diff)
        layout.addWidget(self._prompt, 2)

        layout.addWidget(QLabel("Changes (diff)"))
        self._diff = QTextBrowser()
        self._diff.setMaximumHeight(200)
        layout.addWidget(self._diff, 1)

        self._status = QLabel("")
        self._status.setObjectName("statusLine")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QHBoxLayout()
        self._reset = QPushButton("Reset to default")
        self._reset.setEnabled(bool(self._data.get("can_reset")))
        self._reset.clicked.connect(self._on_reset)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._on_save)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(self._reset)
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self._refresh_diff()

    def _refresh_diff(self) -> None:
        self._diff.setHtml(_diff_html(self._original_prompt, self._prompt.toPlainText()))

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _fields(self) -> dict:
        sections = [s.strip() for s in self._sections.text().split(",") if s.strip()]
        return {
            "name": self._name.text().strip(),
            "default_provider": self._provider.text().strip(),
            "default_model": self._model.text().strip(),
            "temperature": self._temp.value(),
            "display_order": self._order.value(),
            "owned_sections": sections,
        }

    def _on_save(self) -> None:
        self._set_status("Saving…", "applying")
        _spawn(self._do_save())

    async def _do_save(self) -> None:
        prompt = self._prompt.toPlainText()
        try:
            if self._creating:
                await engine.create_agent(
                    self._key_edit.text(), self._name.text(), prompt, **self._fields()
                )
            elif self._key is not None:
                await engine.update_agent(self._key, system_prompt=prompt, **self._fields())
        except Exception as exc:  # noqa: BLE001 - surface validation errors to the user
            self._set_status(f"⚠ {exc}", "error")
            return
        self.saved.emit()
        self.accept()

    def _on_reset(self) -> None:
        self._set_status("Resetting to default…", "applying")
        _spawn(self._do_reset())

    async def _do_reset(self) -> None:
        if self._key is None:
            return
        try:
            row = await engine.reset_agent(self._key)
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"⚠ {exc}", "error")
            return
        # Reflect the restored values in the form/prompt and clear the diff.
        self._original_prompt = row["system_prompt"]
        self._name.setText(row["name"])
        self._provider.setText(row["default_provider"])
        self._model.setText(row["default_model"])
        self._temp.setValue(float(row["temperature"]))
        self._order.setValue(int(row["display_order"]))
        self._sections.setText(", ".join(row["owned_sections"]))
        self._prompt.setPlainText(row["system_prompt"])
        self._set_status("✓ Reset to shipped default.", "ok")
        self.saved.emit()
