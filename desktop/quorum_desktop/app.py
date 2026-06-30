"""Desktop entrypoint: bootstrap env -> migrate local DB -> start the Qt/qasync loop.

Environment must be configured BEFORE importing any quorum_core runtime module, because
quorum_core.core.db builds the engine from settings at import time.
"""

from __future__ import annotations

import os
import sys


def _bootstrap_env() -> None:
    from quorum_desktop.paths import database_url, ensure_encryption_key

    os.environ.setdefault("QUORUM_DATABASE_URL", database_url())
    os.environ.setdefault("QUORUM_ENCRYPTION_KEY", ensure_encryption_key())


def _selftest() -> int:
    """Headless smoke for a frozen bundle: migrate + run a council in test-model mode.

    Verifies that agent_prompts, migrations, and the provider SDKs are all bundled.
    """
    import asyncio
    import tempfile

    os.environ["QUORUM_USE_TEST_MODEL"] = "1"
    os.environ["QUORUM_DATABASE_URL"] = f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/selftest.db"
    from quorum_core.migrate import upgrade_to_head

    upgrade_to_head()
    from quorum_desktop import engine

    async def run() -> int:
        cid = await engine.create_chat("selftest", "Validate the bundle", [("d.md", "ctx")])
        await engine.run(cid)
        d = await engine.get_chat(cid)
        ok = d is not None and bool(d["report_markdown"]) and len(d["runs"]) == 8
        print("SELFTEST", "OK" if ok else "FAIL")
        return 0 if ok else 1

    return asyncio.run(run())


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    _bootstrap_env()

    # Bring this install's local SQLite up to the schema bundled with quorum_core.
    from quorum_core.migrate import upgrade_to_head

    upgrade_to_head()

    import asyncio

    import qasync
    from PySide6.QtWidgets import QApplication

    from quorum_desktop.theme import apply_theme
    from quorum_desktop.windows.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("quorum-gatherer")
    apply_theme(app)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    close_event = asyncio.Event()
    app.aboutToQuit.connect(close_event.set)

    window = MainWindow()
    window.show()

    # Self-update heartbeat (no-op in dev / before the TUF repo is initialized).
    from quorum_core import __version__
    from quorum_desktop import updater

    updater.schedule_heartbeat(window, __version__)

    with loop:
        loop.run_until_complete(close_event.wait())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
