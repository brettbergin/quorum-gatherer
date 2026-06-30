"""Bridge the core `event_bus` to Qt signals.

The web app forwards orchestrator events over a WebSocket; the desktop app subscribes to
the same in-process bus and re-emits each event as a Qt signal. Because qasync runs asyncio
on Qt's event loop, signal emission happens on the GUI thread — safe for widget updates.
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, Signal
from quorum_core.core.events import event_bus


class CouncilBridge(QObject):
    phase_changed = Signal(str)  # "deliberation" | "synthesis"
    agent_joined = Signal(str, str)  # key, name
    agent_started = Signal(str, str, str)  # key, provider, model
    agent_token = Signal(str, str)  # key, delta
    agent_complete = Signal(str, str)  # key, final text
    agent_failed = Signal(str, str)  # key, error
    council_report = Signal(str, dict)  # markdown, structured content
    deliberation_complete = Signal()  # Phase A done; council paused awaiting the Chairman
    error = Signal(str)
    finished = Signal()

    def __init__(self, chat_id: str) -> None:
        super().__init__()
        self._chat_id = chat_id
        self._queue = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Subscribe synchronously (so no early events are missed) and drain in a task."""
        self._queue = event_bus.subscribe(self._chat_id)
        self._task = asyncio.ensure_future(self._consume())

    async def _consume(self) -> None:
        assert self._queue is not None
        try:
            while True:
                ev = await self._queue.get()
                if self._dispatch(ev):
                    break
        finally:
            event_bus.unsubscribe(self._chat_id, self._queue)

    def _dispatch(self, ev: dict) -> bool:
        """Emit the matching signal. Returns True when the run is terminal."""
        t = ev.get("type")
        if t == "phase_changed":
            self.phase_changed.emit(ev["phase"])
        elif t == "agent_joined":
            self.agent_joined.emit(ev["agent_key"], ev["name"])
        elif t == "agent_run_started":
            self.agent_started.emit(ev["agent_key"], ev.get("provider", ""), ev.get("model", ""))
        elif t == "agent_token":
            self.agent_token.emit(ev["agent_key"], ev["delta"])
        elif t == "agent_run_complete":
            self.agent_complete.emit(ev["agent_key"], ev["text"])
        elif t == "agent_run_failed":
            self.agent_failed.emit(ev["agent_key"], ev["error"])
        elif t == "council_report":
            self.council_report.emit(ev["markdown"], ev["content"])
            self.finished.emit()
            return True
        elif t == "deliberation_complete":
            self.deliberation_complete.emit()
            self.finished.emit()
            return True
        elif t == "error":
            self.error.emit(ev["message"])
            self.finished.emit()
            return True
        return False

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
