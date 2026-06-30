"""PyInstaller entry point for the quorum-gatherer desktop app."""

import os

# logfire registers a pydantic plugin that calls inspect.getsource (unavailable in a
# frozen bundle). We don't use it — disable pydantic plugins before any pydantic import.
os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "1")

from quorum_desktop.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
