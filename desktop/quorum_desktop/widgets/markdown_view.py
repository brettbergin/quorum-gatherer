"""A QTextBrowser that renders Markdown with readable block spacing.

Qt's `setMarkdown` builds the document via its Markdown importer, which applies tight block
margins and ignores `setDefaultStyleSheet` (CSS only affects the `setHtml` path). So after parsing
we walk the blocks and set sensible top/bottom margins per block type, plus a little line height.
"""

from __future__ import annotations

from PySide6.QtGui import QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QTextBrowser


class MarkdownView(QTextBrowser):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(True)

    def setMarkdown(self, markdown: str) -> None:  # noqa: N802 - Qt override
        super().setMarkdown(markdown or "")
        self._apply_spacing()

    def _apply_spacing(self) -> None:
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        block = doc.begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if level == 1:
                top, bottom = 22, 8
            elif level == 2:
                top, bottom = 18, 6
            elif level >= 3:
                top, bottom = 14, 4
            elif block.textList() is not None:
                top, bottom = 3, 3
            else:
                top, bottom = 8, 8

            margins = QTextBlockFormat()
            margins.setTopMargin(top)
            margins.setBottomMargin(bottom)
            margins.setLineHeight(125, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            cursor.setPosition(block.position())
            cursor.mergeBlockFormat(margins)
            block = block.next()
        cursor.endEditBlock()
