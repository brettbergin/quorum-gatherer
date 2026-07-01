"""Coverage for the per-user paths/encryption-key helpers."""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet
from quorum_desktop import paths


def test_data_dir_created(tmp_path, monkeypatch):
    target = tmp_path / "userdata"
    monkeypatch.setattr(paths.platformdirs, "user_data_dir", lambda *a, **k: str(target))
    d = paths.data_dir()
    assert d == target
    assert d.is_dir()


def test_db_path_and_url(tmp_path, monkeypatch):
    target = tmp_path / "ud"
    monkeypatch.setattr(paths.platformdirs, "user_data_dir", lambda *a, **k: str(target))
    p = paths.db_path()
    assert p == target / "quorum.db"
    url = paths.database_url()
    assert url == f"sqlite+aiosqlite:///{p}"
    assert url.startswith("sqlite+aiosqlite:///")


def test_ensure_encryption_key_generates_then_reuses(tmp_path, monkeypatch):
    target = tmp_path / "ud"
    monkeypatch.setattr(paths.platformdirs, "user_data_dir", lambda *a, **k: str(target))

    key1 = paths.ensure_encryption_key()
    # Valid Fernet key (round-trips).
    Fernet(key1.encode())
    assert (target / "secret.key").exists()

    # A second call returns the persisted key, not a fresh one.
    key2 = paths.ensure_encryption_key()
    assert key2 == key1


def test_ensure_encryption_key_chmod_failure_suppressed(tmp_path, monkeypatch):
    target = tmp_path / "ud"
    monkeypatch.setattr(paths.platformdirs, "user_data_dir", lambda *a, **k: str(target))

    def boom(*a, **k):
        raise OSError("no chmod on this fs")

    monkeypatch.setattr(paths.os, "chmod", boom)
    key = paths.ensure_encryption_key()  # OSError is suppressed
    assert isinstance(key, str) and key
    assert Path(target / "secret.key").exists()
