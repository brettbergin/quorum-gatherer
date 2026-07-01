"""Headless (offscreen) coverage tests for the desktop GUI dialog modules.

These construct each dialog with realistic mock data and exercise the synchronous
constructors plus the simple handlers. Anything that needs a running qasync loop or
network (engine coroutines, `_spawn`) is patched so the handler body runs without a
live event loop or real I/O.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from quorum_desktop.widgets import (
    agent_chat_dialog,
    agent_edit_dialog,
    report_dialog,
)
from quorum_desktop.widgets.agent_chat_dialog import AgentChatDialog
from quorum_desktop.widgets.agent_edit_dialog import AgentEditDialog, _diff_html
from quorum_desktop.widgets.chairman_report import ChairmanReport
from quorum_desktop.widgets.report_dialog import ChairmanReportDialog, _export_document
from quorum_desktop.widgets.transaction_dialog import AgentTransactionDialog

# --------------------------------------------------------------------- agent_chat_dialog


def _chat_data(with_turns: bool = True) -> dict:
    data = {
        "agent_name": "The Economist",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    if with_turns:
        data["turns"] = [
            {"role": "agent", "content": "# Position\n\nHere is my **take**."},
            {"role": "user", "content": "What about cost?"},
            {"role": "agent", "content": "Cost is manageable."},
        ]
    return data


def test_agent_chat_dialog_with_turns(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data(with_turns=True))
    qtbot.addWidget(w)
    assert "The Economist" in w.windowTitle()
    assert w._meta.text() == "anthropic · claude-sonnet-4-6"


def test_agent_chat_dialog_no_turns(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", {"agent_name": "Solo"})
    qtbot.addWidget(w)
    # falls back to the "hasn't deliberated yet" bubble
    assert w._meta.text() == ""


def test_agent_chat_dialog_fallback_name(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", {})
    qtbot.addWidget(w)
    assert w._agent_name == "economist"


def test_agent_chat_live_stream(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    w.begin_live("partial")
    assert w._live_view is not None
    w.append_live(" more")
    w.append_live(" text")
    w.end_live("final **markdown**")
    assert w._live_view is None
    assert w._live_acc == []


def test_agent_chat_live_begin_empty_then_append(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    w.begin_live()  # empty initial -> "…"
    w.append_live("hi")
    # end_live with empty text falls back to accumulator
    w.end_live("")
    assert w._live_view is None


def test_agent_chat_append_live_without_begin(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    # append_live should lazily begin a live bubble
    w.append_live("auto-started")
    assert w._live_view is not None


def test_agent_chat_end_live_noop_when_no_live(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    w.end_live("ignored")  # no live view -> no-op
    assert w._live_view is None


def test_agent_chat_on_send_empty_is_noop(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    w._input.setPlainText("   ")
    with patch.object(agent_chat_dialog, "_spawn") as spawn:
        w._on_send()
        spawn.assert_not_called()
    assert w._send.isEnabled()


def test_agent_chat_on_send_spawns(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    w._input.setPlainText("Here is my answer")
    with patch.object(agent_chat_dialog, "_spawn") as spawn:
        w._on_send()
        spawn.assert_called_once()
    assert not w._send.isEnabled()
    assert w._input.toPlainText() == ""


async def test_agent_chat_stream_reply_success(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    view = w._add_bubble("agent", "…")

    async def fake_chat(chat_id, agent_key, text, on_delta):
        await on_delta("partial ")
        await on_delta("reply")
        return "full **reply**"

    with patch.object(agent_chat_dialog.engine, "chat_with_agent", fake_chat):
        await w._stream_reply("question", view)
    assert w._send.isEnabled()


async def test_agent_chat_stream_reply_error(qtbot):
    w = AgentChatDialog(None, "chat-1", "economist", _chat_data())
    qtbot.addWidget(w)
    view = w._add_bubble("agent", "…")

    async def boom(*args, **kwargs):
        raise RuntimeError("network down")

    with patch.object(agent_chat_dialog.engine, "chat_with_agent", boom):
        await w._stream_reply("question", view)
    assert w._send.isEnabled()


async def test_module_spawn_helper_runs(qtbot):
    # Cover the module-level _spawn helper directly (needs a running loop).
    import asyncio

    async def noop():
        return 1

    agent_chat_dialog._spawn(noop())
    await asyncio.sleep(0)


# --------------------------------------------------------------------- agent_edit_dialog


def _agent_data() -> dict:
    return {
        "key": "economist",
        "name": "The Economist",
        "default_provider": "anthropic",
        "default_model": "claude-sonnet-4-6",
        "temperature": 0.4,
        "display_order": 10,
        "owned_sections": ["cost", "roi"],
        "system_prompt": "You are an economist.",
        "role": "council_member",
        "can_reset": True,
    }


def test_diff_html_no_changes():
    assert "No changes" in _diff_html("same", "same")


def test_diff_html_with_changes():
    out = _diff_html("line one\nline two", "line one\nline THREE")
    assert "<pre" in out
    assert "color" in out


def test_agent_edit_dialog_edit_mode(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    assert not w._creating
    assert w._name.text() == "The Economist"
    assert w._sections.text() == "cost, roi"
    assert w._reset.isEnabled()
    assert "Edit" in w.windowTitle()


def test_agent_edit_dialog_chairman_protected(qtbot):
    data = _agent_data()
    data["role"] = "chairman"
    w = AgentEditDialog(None, data)
    qtbot.addWidget(w)
    assert not w._creating


def test_agent_edit_dialog_create_mode(qtbot):
    w = AgentEditDialog(None, None)
    qtbot.addWidget(w)
    assert w._creating
    assert hasattr(w, "_key_edit")
    assert "Add agent" in w.windowTitle()
    assert not w._reset.isEnabled()


def test_agent_edit_fields_and_diff(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    fields = w._fields()
    assert fields["name"] == "The Economist"
    assert fields["owned_sections"] == ["cost", "roi"]
    # editing the prompt refreshes the diff
    w._prompt.setPlainText("Changed prompt body")
    assert "pre" in w._diff.toHtml()


def test_agent_edit_set_status(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    w._set_status("Saving…", "applying")
    assert w._status.text() == "Saving…"
    assert w._status.property("state") == "applying"


def test_agent_edit_on_save_spawns(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    with patch.object(agent_edit_dialog, "_spawn") as spawn:
        w._on_save()
        spawn.assert_called_once()
    assert w._status.text() == "Saving…"


def test_agent_edit_on_reset_spawns(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    with patch.object(agent_edit_dialog, "_spawn") as spawn:
        w._on_reset()
        spawn.assert_called_once()


async def test_agent_edit_do_save_update(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    saved = []
    w.saved.connect(lambda: saved.append(True))

    async def fake_update(key, **kwargs):
        return {}

    with patch.object(agent_edit_dialog.engine, "update_agent", fake_update):
        await w._do_save()
    assert saved == [True]


async def test_agent_edit_do_save_create(qtbot):
    w = AgentEditDialog(None, None)
    qtbot.addWidget(w)
    w._key_edit.setText("newkey")
    w._name.setText("New Agent")
    saved = []
    w.saved.connect(lambda: saved.append(True))

    captured = {}

    async def fake_create(key, name, prompt, **kwargs):
        captured["key"] = key
        captured["name"] = name
        captured["kwargs"] = kwargs
        return {}

    with patch.object(agent_edit_dialog.engine, "create_agent", fake_create):
        await w._do_save()
    assert saved == [True], w._status.text()
    assert captured["key"] == "newkey"
    # name is passed positionally, and must NOT be duplicated into the field kwargs.
    assert captured["name"] == "New Agent"
    assert "name" not in captured["kwargs"]


async def test_agent_edit_do_save_error(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)

    async def boom(*a, **k):
        raise ValueError("bad provider")

    with patch.object(agent_edit_dialog.engine, "update_agent", boom):
        await w._do_save()
    assert "bad provider" in w._status.text()


async def test_agent_edit_do_reset_success(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)
    row = {
        "system_prompt": "restored",
        "name": "Restored Name",
        "default_provider": "anthropic",
        "default_model": "claude-sonnet-4-6",
        "temperature": 0.2,
        "display_order": 5,
        "owned_sections": ["a"],
    }

    async def fake_reset(key):
        return row

    with patch.object(agent_edit_dialog.engine, "reset_agent", fake_reset):
        await w._do_reset()
    assert w._name.text() == "Restored Name"
    assert "default" in w._status.text()


async def test_agent_edit_do_reset_no_key(qtbot):
    w = AgentEditDialog(None, None)  # creating -> key is None
    qtbot.addWidget(w)
    # _do_reset returns immediately when key is None
    await w._do_reset()


async def test_agent_edit_do_reset_error(qtbot):
    w = AgentEditDialog(None, _agent_data())
    qtbot.addWidget(w)

    async def boom(key):
        raise RuntimeError("cannot reset")

    with patch.object(agent_edit_dialog.engine, "reset_agent", boom):
        await w._do_reset()
    assert "cannot reset" in w._status.text()


# --------------------------------------------------------------------- transaction_dialog


def _txn_data(error: bool = False) -> dict:
    data = {
        "agent_name": "The Strategist",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "status": "AgentRunStatus.completed",
        "system": "System instructions here.",
        "prompt": "The prompt that was sent.",
        "response": "The model response.",
        "prompt_tokens": 1200,
        "completion_tokens": 350,
        "latency_ms": 4200,
    }
    if error:
        data["response"] = ""
        data["error"] = "rate limited"
    return data


def test_transaction_dialog_full(qtbot):
    w = AgentTransactionDialog(None, _txn_data())
    qtbot.addWidget(w)
    assert "The Strategist" in w.windowTitle()


def test_transaction_dialog_error(qtbot):
    w = AgentTransactionDialog(None, _txn_data(error=True))
    qtbot.addWidget(w)
    assert "Strategist" in w.windowTitle()


def test_transaction_dialog_empty(qtbot):
    w = AgentTransactionDialog(None, {})
    qtbot.addWidget(w)
    assert "Agent" in w.windowTitle()


def test_transaction_meta_line():
    line = AgentTransactionDialog._meta_line(_txn_data())
    assert "anthropic" in line
    assert "completed" in line
    assert "tokens" in line
    assert "ms" in line


def test_transaction_meta_line_empty():
    assert AgentTransactionDialog._meta_line({}) == ""


# --------------------------------------------------------------------- chairman_report


def test_chairman_report_construct(qtbot):
    w = ChairmanReport()
    qtbot.addWidget(w)
    assert w._markdown == ""


def test_chairman_report_set_markdown_and_reset(qtbot):
    w = ChairmanReport()
    qtbot.addWidget(w)
    w.set_markdown("# Report\n\nFinal recommendation.")
    assert w._markdown.startswith("# Report")
    assert w._expand.isEnabled()
    w.reset()
    assert w._markdown == ""
    assert not w._expand.isEnabled()


def test_chairman_report_set_markdown_empty(qtbot):
    w = ChairmanReport()
    qtbot.addWidget(w)
    w.set_markdown("")
    assert not w._expand.isEnabled()


def test_chairman_report_convene_enabled(qtbot):
    w = ChairmanReport()
    qtbot.addWidget(w)
    w.set_convene_enabled(True)
    assert w._convene.isEnabled()
    w.set_convene_enabled(False)
    assert not w._convene.isEnabled()


def test_chairman_report_synthesizing(qtbot):
    w = ChairmanReport()
    qtbot.addWidget(w)
    w.set_synthesizing(True)
    assert "synthesizing" in w._status.text()
    w.set_synthesizing(False)
    assert w._status.text() == ""


def test_chairman_report_signals(qtbot):
    w = ChairmanReport()
    qtbot.addWidget(w)
    convened = []
    expanded = []
    w.convene_requested.connect(lambda: convened.append(True))
    w.expand_requested.connect(lambda md: expanded.append(md))
    w.set_markdown("body")
    w.set_convene_enabled(True)
    w._convene.click()
    w._expand.click()
    assert convened == [True]
    assert expanded == ["body"]


# --------------------------------------------------------------------- report_dialog


def test_export_document():
    doc = _export_document("# Title\n\nSome text.")
    assert "Title" in doc.toPlainText()


def test_export_document_empty():
    doc = _export_document("")
    assert doc.toPlainText() == ""


def test_chairman_report_dialog_construct(qtbot):
    w = ChairmanReportDialog(None, "# Final\n\nThe recommendation.")
    qtbot.addWidget(w)
    assert "Chairman" in w.windowTitle()
    assert w._markdown.startswith("# Final")


def test_chairman_report_dialog_none_markdown(qtbot):
    w = ChairmanReportDialog(None, "")
    qtbot.addWidget(w)
    assert w._markdown == ""


def test_report_dialog_export_html_cancelled(qtbot):
    w = ChairmanReportDialog(None, "# Report")
    qtbot.addWidget(w)
    with patch.object(report_dialog.QFileDialog, "getSaveFileName", return_value=("", "")):
        w._export_html()  # cancelled -> no write


def test_report_dialog_export_html_writes(qtbot, tmp_path):
    out = tmp_path / "report.html"
    w = ChairmanReportDialog(None, "# Report\n\nbody")
    qtbot.addWidget(w)
    with (
        patch.object(report_dialog.QFileDialog, "getSaveFileName", return_value=(str(out), "")),
        patch.object(report_dialog.QMessageBox, "information") as info,
    ):
        w._export_html()
    assert out.exists()
    assert "Report" in out.read_text(encoding="utf-8")
    info.assert_called_once()


def test_report_dialog_export_pdf_cancelled(qtbot):
    w = ChairmanReportDialog(None, "# Report")
    qtbot.addWidget(w)
    with patch.object(report_dialog.QFileDialog, "getSaveFileName", return_value=("", "")):
        w._export_pdf()


def test_report_dialog_export_pdf_writes(qtbot, tmp_path):
    out = tmp_path / "report.pdf"
    w = ChairmanReportDialog(None, "# Report\n\nbody")
    qtbot.addWidget(w)
    with (
        patch.object(report_dialog.QFileDialog, "getSaveFileName", return_value=(str(out), "")),
        patch.object(report_dialog.QMessageBox, "information") as info,
    ):
        w._export_pdf()
    assert out.exists()
    info.assert_called_once()


def test_report_dialog_write_error(qtbot):
    w = ChairmanReportDialog(None, "# Report")
    qtbot.addWidget(w)

    def boom():
        raise OSError("disk full")

    with patch.object(report_dialog.QMessageBox, "warning") as warn:
        w._write("/some/path", boom)
    warn.assert_called_once()


# --------------------------------------------------------------------- settings_dialog


async def test_settings_dialog_construct(qtbot, db):
    # ProvidersPage.__init__ spawns engine.provider_state() via asyncio.ensure_future,
    # so a running loop (async test) and a seeded DB are needed.
    from quorum_desktop.widgets.settings_dialog import SettingsDialog

    with patch("quorum_desktop.updater.updates_supported", return_value=False):
        w = SettingsDialog(None)
        qtbot.addWidget(w)
        assert w._nav.count() == 3
        assert w._stack.count() == 3
        w._nav.setCurrentRow(1)
        assert w._stack.currentIndex() == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
