"""Idea composer + context-doc upload (mirrors the web Composer)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class Composer(QFrame):
    submit = Signal(str)  # idea text
    upload = Signal(str)  # file path

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        outer = QVBoxLayout(self)

        self._idea = QPlainTextEdit()
        self._idea.setPlaceholderText(
            "Describe the product strategy idea to put before the council…"
        )
        self._idea.setFixedHeight(80)
        self._idea.textChanged.connect(self._update_enabled)
        outer.addWidget(self._idea)

        row = QHBoxLayout()
        doc_btn = QPushButton("+ Context doc")
        doc_btn.clicked.connect(self._pick_file)
        self._docs = QLabel("")
        self._docs.setObjectName("muted")
        self._convene = QPushButton("Begin deliberation")
        self._convene.setObjectName("primary")
        self._convene.setEnabled(False)  # nothing to deliberate on until there's input
        self._convene.clicked.connect(self._on_submit)
        row.addWidget(doc_btn)
        row.addWidget(self._docs, 1)
        row.addWidget(self._convene)
        outer.addLayout(row)
        self._running = False

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a context document", "", "Text (*.txt *.md *.markdown);;All files (*)"
        )
        if path:
            self.upload.emit(path)

    def _on_submit(self) -> None:
        idea = self._idea.toPlainText().strip()
        if idea:
            self.submit.emit(idea)

    def _update_enabled(self) -> None:
        # Enabled only when there's something to deliberate on (and no run in flight).
        self._convene.setEnabled(
            not self._running and bool(self._idea.toPlainText().strip())
        )

    def set_idea(self, text: str) -> None:
        self._idea.setPlainText(text or "")

    def set_documents(self, filenames: list[str]) -> None:
        self._docs.setText("  ".join(f"📎 {n}" for n in filenames))

    def set_running(self, running: bool) -> None:
        self._running = running
        self._convene.setText("Council in session…" if running else "Begin deliberation")
        self._update_enabled()
