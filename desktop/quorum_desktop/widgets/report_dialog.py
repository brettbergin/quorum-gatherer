"""Modal showing the Chairman's final report in full, rendered from Markdown."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from quorum_desktop.widgets.markdown_view import MarkdownView


class ChairmanReportDialog(QDialog):
    """Full-screen-ish read-only view of the Chairman's synthesis report."""

    def __init__(self, parent, markdown: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("The Chairman — Final Report")
        self.setMinimumSize(QSize(900, 720))

        layout = QVBoxLayout(self)

        title = QLabel("⚖️  The Chairman — Final Report")
        title.setObjectName("chairTitle")
        layout.addWidget(title)

        body = MarkdownView()
        body.setMarkdown(markdown or "")
        layout.addWidget(body, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
