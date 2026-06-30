"""Chat modal for one council member: a conversation thread + an input box.

Phase-2 of the council flow. The thread opens with the original idea and the agent's contribution;
the user answers the agent's clarifying questions / supplies context and the same agent replies
(streamed). Turns are persisted so the Chairman can later synthesize each agent's updated position.
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from quorum_desktop import engine
from quorum_desktop.widgets.markdown_view import MarkdownView

BUBBLE_MAX = 560  # px — keeps messages from spanning the full dialog width


def _spawn(coro) -> None:
    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)


class _BubbleBody(MarkdownView):
    """A markdown view that grows to fit its content (no inner scrollbar) — one chat bubble."""

    def __init__(self) -> None:
        super().__init__()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(0)
        # Reset the global QTextBrowser padding/border from the theme: the enclosing bubble
        # QFrame already supplies the inner margins, and any padding here is space that _fit()
        # doesn't account for (it sizes to document().size()), which clips/pads every message.
        self.setStyleSheet("background:transparent; border:none; padding:0;")

    def setMarkdown(self, markdown: str) -> None:  # noqa: N802 - Qt override
        super().setMarkdown(markdown)
        self._fit()

    def setPlainText(self, text: str) -> None:  # noqa: N802 - Qt override
        super().setPlainText(text)
        self._fit()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._fit()

    def _fit(self) -> None:
        width = self.viewport().width()
        if width <= 0:
            return
        self.document().setTextWidth(width)
        self.setFixedHeight(int(self.document().size().height()) + 2)


class AgentChatDialog(QDialog):
    def __init__(self, parent, chat_id: str, agent_key: str, data: dict) -> None:
        super().__init__(parent)
        self._chat_id = chat_id
        self._agent_key = agent_key
        self._agent_name = data.get("agent_name") or agent_key
        self.setWindowTitle(f"{self._agent_name} — discussion")
        self.setMinimumSize(QSize(640, 520))
        self.resize(960, 820)
        # the in-progress agent bubble while it streams a live deliberation
        self._live_view: _BubbleBody | None = None
        self._live_acc: list[str] = []

        layout = QVBoxLayout(self)
        title = QLabel(self._agent_name)
        title.setStyleSheet("font-size:16px; font-weight:700;")
        layout.addWidget(title)
        self._meta = QLabel("")
        self._meta.setObjectName("muted")
        layout.addWidget(self._meta)

        # Scrollable conversation thread.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._thread = QWidget()
        self._thread_layout = QVBoxLayout(self._thread)
        self._thread_layout.setSpacing(12)
        self._thread_layout.addStretch(1)
        self._scroll.setWidget(self._thread)
        layout.addWidget(self._scroll, 1)

        # Input row: the composer, with Send (top) and Close (bottom) stacked in an aligned column.
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("Answer the agent's questions or add context…")
        self._input.setFixedHeight(84)
        self._send = QPushButton("Send")
        self._send.setObjectName("primary")
        self._send.setFixedWidth(92)
        self._send.clicked.connect(self._on_send)
        close = QPushButton("Close")
        close.setFixedWidth(92)
        close.clicked.connect(self.accept)

        buttons = QVBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self._send)
        buttons.addStretch(1)
        buttons.addWidget(close)

        input_row = QHBoxLayout()
        input_row.addWidget(self._input, 1)
        input_row.addLayout(buttons)
        layout.addLayout(input_row)

        self._render(data)

    # ---------------------------------------------------------------- thread rendering
    def _render(self, data: dict) -> None:
        provider, model = data.get("provider"), data.get("model")
        if provider or model:
            self._meta.setText(f"{provider or '?'} · {model or '?'}")
        turns = data.get("turns", [])
        if not turns:
            self._add_bubble("agent", "_This agent hasn't deliberated yet._")
            return
        for turn in turns:
            self._add_bubble(turn["role"], turn["content"])

    def _add_bubble(self, role: str, content: str) -> _BubbleBody:
        is_user = role == "user"
        bubble = QFrame()
        bubble.setObjectName("userBubble" if is_user else "agentBubble")
        bubble.setMaximumWidth(BUBBLE_MAX)
        v = QVBoxLayout(bubble)
        v.setContentsMargins(12, 8, 12, 10)
        v.setSpacing(4)

        who = QLabel("You" if is_user else self._agent_name)
        who.setObjectName("muted" if is_user else "agentName")
        v.addWidget(who)

        # Both sides render markdown (auto-height, no inner scrollbar).
        body = _BubbleBody()
        body.setMarkdown(content)
        v.addWidget(body)

        # Align user bubbles right, agent bubbles left; cap their width.
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if is_user:
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        self._thread_layout.insertWidget(self._thread_layout.count() - 1, container)
        return body

    # --- live deliberation streaming (agent still running when the dialog is opened) ---
    def begin_live(self, initial: str = "") -> None:
        self._live_acc = [initial] if initial else []
        self._live_view = self._add_bubble("agent", initial or "…")
        if initial:
            self._live_view.setPlainText(initial)
        self._scroll_to_bottom()

    def append_live(self, delta: str) -> None:
        if self._live_view is None:
            self.begin_live()
        self._live_acc.append(delta)
        if self._live_view is not None:
            self._live_view.setPlainText("".join(self._live_acc))
        self._scroll_to_bottom()

    def end_live(self, text: str) -> None:
        if self._live_view is None:
            return
        self._live_view.setMarkdown(text or "".join(self._live_acc))
        self._live_view = None
        self._live_acc = []
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # ---------------------------------------------------------------- send
    def _on_send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self._send.setEnabled(False)
        self._add_bubble("user", text)
        reply_view = self._add_bubble("agent", "…")
        self._scroll_to_bottom()
        _spawn(self._stream_reply(text, reply_view))

    async def _stream_reply(self, text: str, reply_view: _BubbleBody) -> None:
        acc: list[str] = []

        async def on_delta(delta: str) -> None:
            acc.append(delta)
            reply_view.setPlainText("".join(acc))  # cheap live update while streaming
            self._scroll_to_bottom()

        try:
            reply = await engine.chat_with_agent(self._chat_id, self._agent_key, text, on_delta)
        except Exception as exc:  # noqa: BLE001 - surface any error in-thread
            reply = f"⚠ {exc}"
        reply_view.setMarkdown(reply or "".join(acc))  # render markdown once complete
        self._send.setEnabled(True)
        self._scroll_to_bottom()
