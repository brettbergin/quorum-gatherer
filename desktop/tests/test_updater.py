"""Coverage for the self-updater helper functions (TUF/network parts mocked)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from quorum_desktop import updater


def test_os_tag_known_and_unknown():
    with patch("quorum_desktop.updater.platform.system", return_value="Darwin"):
        assert updater._os_tag() == "macos"
    with patch("quorum_desktop.updater.platform.system", return_value="Windows"):
        assert updater._os_tag() == "windows"
    with patch("quorum_desktop.updater.platform.system", return_value="Linux"):
        assert updater._os_tag() == "linux"
    with patch("quorum_desktop.updater.platform.system", return_value="Plan9"):
        assert updater._os_tag() == "other"


def test_is_frozen_reflects_sys_attr(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert updater.is_frozen() is False
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert updater.is_frozen() is True


def test_bundled_root_present(tmp_path, monkeypatch):
    base = tmp_path
    (base / "tuf").mkdir()
    root = base / "tuf" / "root.json"
    root.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(base), raising=False)
    assert updater._bundled_root() == root


def test_bundled_root_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert updater._bundled_root() is None


def test_install_dir_non_darwin(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater.sys, "executable", "/opt/app/bin/quorum")
    assert updater._install_dir() == Path("/opt/app/bin")


def test_install_dir_darwin_bundle(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    exe = "/Applications/Quorum.app/Contents/MacOS/quorum"
    monkeypatch.setattr(updater.sys, "executable", exe)
    # install dir is the folder containing the .app bundle
    assert updater._install_dir() == Path("/Applications")


# --------------------------------------------------------------------- not-frozen short circuits


def test_check_and_apply_not_frozen(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    assert updater.check_and_apply("1.0.0") is False


def test_available_update_not_frozen(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    assert updater.available_update("1.0.0") is None


def test_updates_supported_not_frozen(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    assert updater.updates_supported() is False


def test_schedule_heartbeat_not_frozen(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    parent = SimpleNamespace()
    updater.schedule_heartbeat(parent, "1.0.0")
    assert not hasattr(parent, "_update_timer")


# --------------------------------------------------------------------- frozen paths (mocked client)


def test_make_client_no_bundled_root_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_bundled_root", lambda: None)
    with patch("quorum_desktop.paths.data_dir", return_value=tmp_path):
        assert updater._make_client("1.0.0") is None


def test_make_client_builds_client(tmp_path, monkeypatch):
    # Provide a bundled root that gets copied into the metadata dir.
    bundled = tmp_path / "bundled-root.json"
    bundled.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(updater, "_bundled_root", lambda: bundled)
    monkeypatch.setattr(updater, "_install_dir", lambda: tmp_path / "install")

    fake_client = MagicMock(name="Client")
    fake_module = SimpleNamespace(Client=MagicMock(return_value=fake_client))
    with (
        patch("quorum_desktop.paths.data_dir", return_value=tmp_path),
        patch.dict(sys.modules, {"tufup.client": fake_module}),
    ):
        client = updater._make_client("1.2.3")

    assert client is fake_client
    # Root metadata seeded from the bundled copy.
    assert (tmp_path / "tuf" / "metadata" / "root.json").exists()
    fake_module.Client.assert_called_once()


def test_check_and_apply_no_client(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "_make_client", lambda v: None)
    assert updater.check_and_apply("1.0.0") is False


def test_check_and_apply_no_update(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    client = MagicMock()
    client.check_for_updates.return_value = None
    monkeypatch.setattr(updater, "_make_client", lambda v: client)
    assert updater.check_and_apply("1.0.0") is False


def test_check_and_apply_found_and_applied(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    client = MagicMock()
    client.check_for_updates.return_value = object()
    monkeypatch.setattr(updater, "_make_client", lambda v: client)
    assert updater.check_and_apply("1.0.0", apply=True) is True
    client.download_and_apply_update.assert_called_once_with(skip_confirmation=True)


def test_check_and_apply_found_no_apply(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    client = MagicMock()
    client.check_for_updates.return_value = object()
    monkeypatch.setattr(updater, "_make_client", lambda v: client)
    assert updater.check_and_apply("1.0.0", apply=False) is True
    client.download_and_apply_update.assert_not_called()


def test_apply_update_delegates(monkeypatch):
    monkeypatch.setattr(updater, "check_and_apply", lambda v, *, apply: (v, apply))
    assert updater.apply_update("9.9.9") == ("9.9.9", True)


def test_updates_supported_frozen_with_client(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "_make_client", lambda v: MagicMock())
    assert updater.updates_supported() is True


def test_available_update_no_client(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "_make_client", lambda v: None)
    assert updater.available_update("1.0.0") is None


def test_available_update_no_new_update(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    client = MagicMock()
    client.check_for_updates.return_value = None
    monkeypatch.setattr(updater, "_make_client", lambda v: client)
    assert updater.available_update("1.0.0") is None


def test_available_update_with_version_attr(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    client = MagicMock()
    client.check_for_updates.return_value = SimpleNamespace(version="2.0.0")
    monkeypatch.setattr(updater, "_make_client", lambda v: client)
    assert updater.available_update("1.0.0") == "2.0.0"


def test_available_update_without_version_attr(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    client = MagicMock()

    class NoVersion:
        def __str__(self):
            return "blob-3.0.0"

    client.check_for_updates.return_value = NoVersion()
    monkeypatch.setattr(updater, "_make_client", lambda v: client)
    assert updater.available_update("1.0.0") == "blob-3.0.0"


def test_schedule_heartbeat_frozen(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "check_and_apply", lambda v: False)

    timers = []

    class FakeTimer:
        def __init__(self, parent=None):
            self.timeout = MagicMock()
            timers.append(self)

        def timeout_connect(self, fn):  # pragma: no cover - not used
            pass

        def start(self, ms):
            self.started_ms = ms

    fake_qtcore = SimpleNamespace(QTimer=MagicMock())
    instance = MagicMock()
    fake_qtcore.QTimer.return_value = instance

    parent = SimpleNamespace()
    with patch.dict(sys.modules, {"PySide6.QtCore": fake_qtcore}):
        updater.schedule_heartbeat(parent, "1.0.0", interval_hours=6.0)

    # singleShot scheduled the initial tick and a recurring timer was created + started.
    fake_qtcore.QTimer.singleShot.assert_called_once()
    instance.start.assert_called_once()
    assert parent._update_timer is instance
