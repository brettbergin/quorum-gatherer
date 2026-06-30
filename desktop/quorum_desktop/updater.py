"""Self-update via tufup: heartbeat check -> background download -> apply + restart.

Only active in a frozen (installed) build. TUF metadata is served from GitHub Pages and
the (large) target archives from GitHub Releases. The trusted public root metadata ships
inside the app bundle; if it is absent (repo not yet initialized), updating is a no-op.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

BASE_APP_NAME = "quorum-gatherer"
GH = "brettbergin/quorum-gatherer"


def _os_tag() -> str:
    return {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
        platform.system(), "other"
    )


# Per-platform TUF streams: tufup names target archives by app+version only, so each OS
# needs its own app name + metadata path to avoid collisions on the shared targets release.
APP_NAME = f"{BASE_APP_NAME}-{_os_tag()}"

METADATA_BASE_URL = os.environ.get(
    "QUORUM_UPDATE_METADATA_URL",
    f"https://brettbergin.github.io/{BASE_APP_NAME}/metadata/{_os_tag()}/",
)
TARGET_BASE_URL = os.environ.get(
    "QUORUM_UPDATE_TARGET_URL",
    f"https://github.com/{GH}/releases/download/updates/",
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundled_root() -> Path | None:
    """The public root.json shipped in the bundle (data file at tuf/root.json)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidate = base / "tuf" / "root.json"
    return candidate if candidate.exists() else None


def _install_dir() -> Path:
    # Directory that holds the installed app (parent of the executable / .app bundle).
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin" and ".app/Contents/MacOS" in str(exe):
        # .../Foo.app/Contents/MacOS/exe -> install dir is the folder containing Foo.app
        return exe.parents[3]
    return exe.parent


def _make_client(current_version: str):
    from tufup.client import Client

    from quorum_desktop.paths import data_dir

    base = data_dir() / "tuf"
    metadata_dir = base / "metadata"
    target_dir = base / "targets"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Seed the trusted root on first run from the bundled public root metadata.
    root = metadata_dir / "root.json"
    if not root.exists():
        bundled = _bundled_root()
        if bundled is None:
            return None  # repo not initialized yet -> updates disabled
        shutil.copy(bundled, root)

    return Client(
        app_name=APP_NAME,
        app_install_dir=str(_install_dir()),
        current_version=current_version,
        metadata_dir=str(metadata_dir),
        metadata_base_url=METADATA_BASE_URL,
        target_dir=str(target_dir),
        target_base_url=TARGET_BASE_URL,
        refresh_required=False,
    )


def check_and_apply(current_version: str, *, apply: bool = True) -> bool:
    """Return True if an update was found (and applied/restarted when apply=True).

    A no-op outside a frozen build or before the TUF repo exists.
    """
    if not is_frozen():
        return False
    client = _make_client(current_version)
    if client is None:
        return False
    new_update = client.check_for_updates()
    if not new_update:
        return False
    if apply:
        # Downloads, verifies, applies, and relaunches the app.
        client.download_and_apply_update(skip_confirmation=True)
    return True


def updates_supported() -> bool:
    """True when this build can self-update (frozen + TUF root present)."""
    return is_frozen() and _make_client("0.0.0") is not None


def available_update(current_version: str) -> str | None:
    """Return the available newer version string, or None. Blocking (run off the UI thread)."""
    if not is_frozen():
        return None
    client = _make_client(current_version)
    if client is None:
        return None
    new_update = client.check_for_updates()
    if not new_update:
        return None
    version = getattr(new_update, "version", None)
    return str(version) if version else str(new_update)


def apply_update(current_version: str) -> bool:
    """Download + apply the latest update and relaunch. Blocking (run off the UI thread)."""
    return check_and_apply(current_version, apply=True)


def schedule_heartbeat(parent, current_version: str, interval_hours: float = 6.0) -> None:
    """Check shortly after launch and then on a cadence (frozen builds only)."""
    if not is_frozen():
        return
    import contextlib

    from PySide6.QtCore import QTimer

    def tick() -> None:
        with contextlib.suppress(Exception):  # never let an update check crash the app
            check_and_apply(current_version)

    QTimer.singleShot(5_000, tick)
    timer = QTimer(parent)
    timer.timeout.connect(tick)
    timer.start(int(interval_hours * 3600 * 1000))
    parent._update_timer = timer  # keep a reference
