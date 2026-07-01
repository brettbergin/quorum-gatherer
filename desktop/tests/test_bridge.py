"""Coverage for CouncilBridge (event_bus -> Qt signal mapping).

A QApplication is required to instantiate QObject subclasses; conftest forces the
offscreen platform. Signals are captured by connecting plain Python callbacks.
"""

from __future__ import annotations

import asyncio

import pytest
from PySide6.QtWidgets import QApplication
from quorum_core.core.events import event_bus
from quorum_desktop.bridge import CouncilBridge


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _capture(signal):
    received = []
    signal.connect(lambda *a: received.append(a))
    return received


def test_dispatch_phase_changed():
    b = CouncilBridge("c1")
    got = _capture(b.phase_changed)
    assert b._dispatch({"type": "phase_changed", "phase": "deliberation"}) is False
    assert got == [("deliberation",)]


def test_dispatch_agent_joined():
    b = CouncilBridge("c1")
    got = _capture(b.agent_joined)
    assert b._dispatch({"type": "agent_joined", "agent_key": "a", "name": "Analyst"}) is False
    assert got == [("a", "Analyst")]


def test_dispatch_agent_started_defaults():
    b = CouncilBridge("c1")
    got = _capture(b.agent_started)
    # provider/model missing -> defaulted to "".
    assert b._dispatch({"type": "agent_run_started", "agent_key": "a"}) is False
    assert got == [("a", "", "")]


def test_dispatch_agent_token():
    b = CouncilBridge("c1")
    got = _capture(b.agent_token)
    assert b._dispatch({"type": "agent_token", "agent_key": "a", "delta": "hi"}) is False
    assert got == [("a", "hi")]


def test_dispatch_agent_complete():
    b = CouncilBridge("c1")
    got = _capture(b.agent_complete)
    assert b._dispatch({"type": "agent_run_complete", "agent_key": "a", "text": "done"}) is False
    assert got == [("a", "done")]


def test_dispatch_agent_failed():
    b = CouncilBridge("c1")
    got = _capture(b.agent_failed)
    assert b._dispatch({"type": "agent_run_failed", "agent_key": "a", "error": "boom"}) is False
    assert got == [("a", "boom")]


def test_dispatch_council_report_is_terminal():
    b = CouncilBridge("c1")
    rep = _capture(b.council_report)
    fin = _capture(b.finished)
    ev = {"type": "council_report", "markdown": "# R", "content": {"k": "v"}}
    assert b._dispatch(ev) is True
    assert rep == [("# R", {"k": "v"})]
    assert fin == [()]


def test_dispatch_deliberation_complete_is_terminal():
    b = CouncilBridge("c1")
    dc = _capture(b.deliberation_complete)
    fin = _capture(b.finished)
    assert b._dispatch({"type": "deliberation_complete"}) is True
    assert dc == [()]
    assert fin == [()]


def test_dispatch_error_is_terminal():
    b = CouncilBridge("c1")
    err = _capture(b.error)
    fin = _capture(b.finished)
    assert b._dispatch({"type": "error", "message": "bad"}) is True
    assert err == [("bad",)]
    assert fin == [()]


def test_dispatch_unknown_type_returns_false():
    b = CouncilBridge("c1")
    assert b._dispatch({"type": "something_else"}) is False
    assert b._dispatch({}) is False


async def test_start_consume_and_terminal_unsubscribes():
    chat_id = "live-chat"
    b = CouncilBridge(chat_id)
    fin = _capture(b.finished)

    b.start()
    # subscribe() ran synchronously, so the queue exists in the bus.
    assert chat_id in event_bus._subscribers

    # Publish a terminal event; the consume task should emit + unsubscribe + exit.
    await event_bus.publish(chat_id, {"type": "error", "message": "x"})
    await asyncio.wait_for(b._task, timeout=2.0)

    assert fin == [()]
    # The consumer unsubscribed on exit.
    assert chat_id not in event_bus._subscribers


async def test_start_then_stop_cancels_task():
    chat_id = "cancel-chat"
    b = CouncilBridge(chat_id)
    b.start()
    assert b._task is not None
    # Let the consume task actually begin awaiting the queue (so its try/finally is entered).
    await asyncio.sleep(0)

    b.stop()
    with pytest.raises(asyncio.CancelledError):
        await b._task
    # finally-block in _consume unsubscribed during cancellation.
    assert chat_id not in event_bus._subscribers


def test_stop_without_start_is_noop():
    b = CouncilBridge("c1")
    b.stop()  # _task is None -> no error
