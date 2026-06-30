"""The Chairman's final report (renders Markdown via QTextBrowser)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from quorum_desktop.widgets.markdown_view import MarkdownView


class ChairmanReport(QFrame):
    EMPTY = "The final recommendation will appear here once the council has deliberated."
    SYNTHESIZING = "The Chairman is weighing the council and drafting the final recommendation…"

    expand_requested = Signal(str)  # emits the current report markdown
    convene_requested = Signal()  # user asked to convene the Chairman (run synthesis)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self._markdown = ""
        outer = QVBoxLayout(self)

        head = QHBoxLayout()
        title = QLabel("⚖️  The Chairman")
        title.setObjectName("chairTitle")
        self._status = QLabel("")
        self._status.setObjectName("muted")
        self._convene = QPushButton("Convene")
        self._convene.setObjectName("primary")
        self._convene.setEnabled(False)
        self._convene.clicked.connect(self.convene_requested.emit)
        self._expand = QPushButton("⤢  View full report")
        self._expand.setEnabled(False)
        self._expand.clicked.connect(lambda: self.expand_requested.emit(self._markdown))
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self._status)
        head.addWidget(self._convene)
        head.addWidget(self._expand)
        outer.addLayout(head)

        self._body = MarkdownView()
        self._body.setMinimumHeight(260)
        self._body.setMarkdown("")
        self._body.setPlaceholderText(self.EMPTY)
        outer.addWidget(self._body, 1)

    def reset(self) -> None:
        self._status.setText("")
        self._markdown = ""
        self._expand.setEnabled(False)
        self._body.setMarkdown("")

    def set_convene_enabled(self, on: bool) -> None:
        self._convene.setEnabled(on)

    def set_synthesizing(self, on: bool) -> None:
        self._status.setText("synthesizing…" if on else "")
        if on and not self._body.toMarkdown().strip():
            self._body.setMarkdown(f"_{self.SYNTHESIZING}_")

    def set_markdown(self, markdown: str) -> None:
        self._status.setText("")
        self._markdown = markdown or ""
        self._expand.setEnabled(bool(self._markdown.strip()))
        self._body.setMarkdown(markdown)
