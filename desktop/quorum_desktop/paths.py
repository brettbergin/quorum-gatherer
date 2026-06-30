"""Per-user file locations for the desktop app: local SQLite + encryption key.

Each install is fully standalone with its own database under the OS user-data dir.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import platformdirs
from cryptography.fernet import Fernet

APP_NAME = "quorum-gatherer"


def data_dir() -> Path:
    d = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "quorum.db"


def database_url() -> str:
    return f"sqlite+aiosqlite:///{db_path()}"


def ensure_encryption_key() -> str:
    """Return this install's Fernet key, generating + persisting one on first run."""
    key_file = data_dir() / "secret.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    key = Fernet.generate_key().decode()
    key_file.write_text(key, encoding="utf-8")
    with contextlib.suppress(OSError):  # best effort on non-POSIX
        os.chmod(key_file, 0o600)
    return key
