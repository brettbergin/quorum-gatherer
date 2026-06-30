"""Updates settings page: show the current version and check for / apply the latest."""

from __future__ import annotations

import asyncio

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from quorum_core import __version__
from quorum_desktop import updater


class UpdatesPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)

        title = QLabel("Updates")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        outer.addWidget(title)

        self._version = QLabel(f"Current version:  v{__version__}")
        outer.addWidget(self._version)

        self._status = QLabel("")
        self._status.setObjectName("statusLine")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        self._button = QPushButton("Check for latest")
        self._button.setObjectName("primary")
        self._button.clicked.connect(self._on_click)
        outer.addWidget(self._button)
        outer.addStretch(1)

        self._new_version: str | None = None
        if not updater.updates_supported():
            self._button.setText("Up to date")
            self._button.setEnabled(False)
            self._set_status("Auto-update applies to installed builds.", "")

    @staticmethod
    def _spawn(coro) -> None:
        asyncio.ensure_future(coro)

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _on_click(self) -> None:
        if self._new_version:
            self._spawn(self._apply())
        else:
            self._spawn(self._check())

    async def _check(self) -> None:
        self._button.setEnabled(False)
        self._button.setText("Checking…")
        self._set_status("Checking for the latest version…", "applying")
        loop = asyncio.get_running_loop()
        new = await loop.run_in_executor(None, updater.available_update, __version__)
        if new:
            self._new_version = new
            self._button.setText("Update & restart")
            self._button.setEnabled(True)
            self._set_status(f"Update available: v{new}", "ok")
        else:
            self._button.setText("Updated")
            self._button.setEnabled(False)
            self._set_status("You're on the latest version.", "ok")

    async def _apply(self) -> None:
        self._button.setEnabled(False)
        self._button.setText("Updating…")
        self._set_status("Downloading and installing the update…", "applying")
        loop = asyncio.get_running_loop()
        # Applies + relaunches the app; if it returns, the update did not proceed.
        await loop.run_in_executor(None, updater.apply_update, __version__)
        self._set_status("Update could not be applied automatically.", "error")
        self._button.setEnabled(True)
        self._button.setText("Update & restart")
