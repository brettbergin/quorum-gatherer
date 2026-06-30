"""Modal showing one agent's complete LLM transaction: system, prompt, and response."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


def _section(title: str, body: str) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(4)
    label = QLabel(title)
    label.setObjectName("agentName")
    v.addWidget(label)
    edit = QPlainTextEdit()
    edit.setReadOnly(True)
    edit.setPlainText(body)
    edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
    v.addWidget(edit, 1)
    return w


class AgentTransactionDialog(QDialog):
    """Read-only view of the system instructions, the prompt sent, and the model's response."""

    def __init__(self, parent, data: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{data.get('agent_name') or 'Agent'} — LLM transaction")
        self.setMinimumSize(QSize(820, 640))

        layout = QVBoxLayout(self)

        title = QLabel(data.get("agent_name") or "Agent")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        layout.addWidget(title)

        meta = QLabel(self._meta_line(data))
        meta.setObjectName("muted")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(_section("System instructions", data.get("system") or "—"))
        splitter.addWidget(_section("Prompt", data.get("prompt") or "—"))
        response = data.get("response") or ""
        error = data.get("error")
        if error and not response:
            splitter.addWidget(_section("Error", error))
        else:
            splitter.addWidget(_section("Response", response or "—"))
        # Give the prompt/response the most room; system instructions stay compact.
        splitter.setSizes([140, 220, 320])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _meta_line(data: dict) -> str:
        parts: list[str] = []
        provider, model = data.get("provider"), data.get("model")
        if provider or model:
            parts.append(f"{provider or '?'} · {model or '?'}")
        if data.get("status"):
            parts.append(str(data["status"]).replace("AgentRunStatus.", ""))
        pt, ct = data.get("prompt_tokens"), data.get("completion_tokens")
        if pt is not None or ct is not None:
            parts.append(f"{pt or 0} in / {ct or 0} out tokens")
        if data.get("latency_ms") is not None:
            parts.append(f"{data['latency_ms']} ms")
        return "   ·   ".join(parts)
