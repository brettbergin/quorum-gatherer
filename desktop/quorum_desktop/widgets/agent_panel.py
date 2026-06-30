"""A single council member's live panel (mirrors the web AgentPanel)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
)


class _ClickableBadge(QLabel):
    """Status badge that emits `clicked` so completed/failed runs can open a detail modal."""

    clicked = Signal()

    def __init__(self, text: str, state: str) -> None:
        super().__init__(text)
        self.setObjectName("badge")
        self.setProperty("state", state)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AgentPanel(QFrame):
    details_requested = Signal(str)  # emits the agent_key when its badge is clicked
    active_toggled = Signal(str, bool)  # agent_key, is_active (per-session activation checkbox)

    def __init__(self, name: str, agent_key: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(170)
        self._key = agent_key

        outer = QVBoxLayout(self)
        head = QHBoxLayout()
        self._active = QCheckBox()
        self._active.setChecked(True)
        self._active.setToolTip("Include this agent in the next deliberation")
        self._active.toggled.connect(
            lambda on: self.active_toggled.emit(self._key, on)
        )
        name_lbl = QLabel(name)
        name_lbl.setObjectName("agentName")
        self._engaged = QLabel("💬")
        self._engaged.setObjectName("muted")
        self._engaged.setToolTip("You've chatted with this agent")
        self._engaged.setVisible(False)
        self._status = _ClickableBadge("pending", "")
        self._status.clicked.connect(self._on_badge_clicked)
        head.addWidget(self._active)
        head.addWidget(name_lbl)
        head.addStretch(1)
        head.addWidget(self._engaged)
        head.addWidget(self._status)
        outer.addLayout(head)

        self._meta = QLabel("")
        self._meta.setObjectName("muted")
        outer.addWidget(self._meta)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setPlaceholderText("waiting to deliberate…")
        outer.addWidget(self._body, 1)

        # The badge opens the discussion at any time (pending/running/completed/failed).
        self._status.setCursor(Qt.CursorShape.PointingHandCursor)
        self._status.setToolTip("Open the discussion with this agent")

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _on_badge_clicked(self) -> None:
        if self._key:
            self.details_requested.emit(self._key)

    def set_active(self, on: bool) -> None:
        self._active.blockSignals(True)
        self._active.setChecked(on)
        self._active.blockSignals(False)

    def is_active(self) -> bool:
        return self._active.isChecked()

    def current_text(self) -> str:
        """Text streamed so far (used to seed a live chat bubble for a running agent)."""
        return self._body.toPlainText()

    def set_chatted(self, on: bool) -> None:
        self._engaged.setVisible(on)

    def reset(self) -> None:
        self._set_status("pending", "")
        self._engaged.setVisible(False)
        self._meta.setText("")
        self._body.clear()

    def set_started(self, provider: str, model: str) -> None:
        self._set_status("running", "running")
        if provider:
            self._meta.setText(f"{provider} · {model}")
        self._body.clear()

    def append_token(self, delta: str) -> None:
        self._set_status("running", "running")
        self._body.moveCursor(self._body.textCursor().MoveOperation.End)
        self._body.insertPlainText(delta)
        sb = self._body.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_complete(self, text: str) -> None:
        self._set_status("completed", "completed")
        self._body.setPlainText(text)

    def set_failed(self, error: str) -> None:
        self._set_status("failed", "failed")
        self._body.setPlainText(error)

    def hydrate(
        self,
        status: str,
        text: str | None,
        provider: str | None,
        model: str | None,
        error: str | None,
    ) -> None:
        if provider:
            self._meta.setText(f"{provider} · {model}")
        if status == "completed":
            self.set_complete(text or "")
        elif status == "failed":
            self.set_failed(error or "failed")
        elif status == "running":
            self._set_status("running", "running")
            self._body.setPlainText(text or "")
        else:
            self.reset()
