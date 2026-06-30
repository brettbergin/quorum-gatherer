"""Modal showing the Chairman's final report in full, with PDF/HTML export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QSize
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from quorum_desktop.widgets.markdown_view import MarkdownView

# Print/export styling for the standalone document (the on-screen view keeps the app theme).
_EXPORT_CSS = """
body { font-family: -apple-system, 'Segoe UI', sans-serif; font-size: 11pt; color: #111; }
h1 { font-size: 20pt; margin: 18pt 0 8pt; }
h2 { font-size: 15pt; margin: 16pt 0 6pt; }
h3 { font-size: 12pt; margin: 12pt 0 4pt; }
p, li { line-height: 140%; }
"""


def _export_document(markdown: str) -> QTextDocument:
    """A standalone, print-styled document built from the report markdown."""
    doc = QTextDocument()
    doc.setDefaultStyleSheet(_EXPORT_CSS)
    doc.setMarkdown(markdown or "")
    return doc


class ChairmanReportDialog(QDialog):
    """Full-screen-ish read-only view of the Chairman's synthesis report."""

    def __init__(self, parent, markdown: str) -> None:
        super().__init__(parent)
        self._markdown = markdown or ""
        self.setWindowTitle("The Chairman — Final Report")
        self.setMinimumSize(QSize(760, 560))
        self.resize(1180, 900)

        layout = QVBoxLayout(self)

        title = QLabel("⚖️  The Chairman — Final Report")
        title.setObjectName("chairTitle")
        layout.addWidget(title)

        body = MarkdownView()
        body.setMarkdown(self._markdown)
        layout.addWidget(body, 1)

        buttons = QHBoxLayout()
        export_html = QPushButton("Export HTML")
        export_html.clicked.connect(self._export_html)
        export_pdf = QPushButton("Export PDF")
        export_pdf.clicked.connect(self._export_pdf)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(export_html)
        buttons.addWidget(export_pdf)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # ---------------------------------------------------------------- export
    def _export_html(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export report as HTML", "chairman-report.html", "HTML (*.html)"
        )
        if not path:
            return
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Chairman — Final Report</title>"
            f"<style>{_EXPORT_CSS}</style></head><body>"
            f"{_export_document(self._markdown).toHtml()}</body></html>"
        )
        self._write(path, lambda: Path(path).write_text(html, encoding="utf-8"))

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export report as PDF", "chairman-report.pdf", "PDF (*.pdf)"
        )
        if not path:
            return

        def write() -> None:
            writer = QPdfWriter(path)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)
            _export_document(self._markdown).print_(writer)

        self._write(path, write)

    def _write(self, path: str, do_write) -> None:
        try:
            do_write()
        except Exception as exc:  # noqa: BLE001 - surface any write/render error to the user
            QMessageBox.warning(self, "Export failed", f"Could not export the report:\n{exc}")
            return
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
