"""Settings modal: a left sidebar of sections + a stacked content area.

Sections: Providers (AI keys), Agents (council roster), Updates. Add more by appending a
(label, widget) pair to the sections list.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
)

from quorum_desktop.widgets.agents_page import AgentsPage
from quorum_desktop.widgets.providers_page import ProvidersPage
from quorum_desktop.widgets.updates_page import UpdatesPage


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(QSize(720, 480))
        self.resize(1060, 740)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("settingsNav")
        self._nav.setFixedWidth(170)
        self._stack = QStackedWidget()

        sections = [
            ("Providers", ProvidersPage()),
            ("Agents", AgentsPage()),
            ("Updates", UpdatesPage()),
        ]
        for label, page in sections:
            self._nav.addItem(label)
            self._stack.addWidget(page)

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)
