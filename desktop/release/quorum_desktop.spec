# PyInstaller spec for the quorum-gatherer desktop app.
#
# Invoked from the desktop/ directory (see release.yml and ci.yml):
#     uv run pyinstaller release/quorum_desktop.spec --noconfirm
#
# Produces a onedir bundle "quorum-gatherer" in desktop/dist/ (used as-is on Windows),
# plus a quorum-gatherer.app on macOS — matching the paths release.yml packages.

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

# SPECPATH is injected by PyInstaller and points at this file's directory
# (.../desktop/release), so paths resolve no matter the current working directory.
DESKTOP = os.path.dirname(SPECPATH)  # noqa: F821 -- SPECPATH is a PyInstaller global

datas = []
binaries = []
hiddenimports = []

# quorum_core reads runtime data from disk by path, so it must be bundled at the same
# package-relative layout the code expects (PACKAGE_DIR / "agent_prompts", "migrations"):
#   - agent_prompts/*.md          council agent definitions (agents/loader.py, seed.py)
#   - migrations/                 Alembic env.py + versions/*.py, run at startup via
#                                 migrate.upgrade_to_head(); Alembic imports these by path,
#                                 so they must ship as real files, not just frozen modules.
datas += collect_data_files("quorum_core")
datas += collect_data_files("quorum_core", include_py_files=True, includes=["migrations/*"])

# These are imported lazily by pydantic-ai's provider backends or pulled in dynamically
# (SQLAlchemy's DBAPI driver + greenlet C-extension), so static analysis misses them.
# Collect each whole, but drop test submodules: google.genai ships a large test suite that
# would otherwise balloon — and stall — the build.
def _is_test_module(name):
    return ".tests" in name or ".test_" in name or name.endswith(".tests")


def _collect(pkg):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:
        return [], [], []  # optional provider extra not installed — fine
    return pkg_datas, pkg_binaries, [m for m in pkg_hidden if not _is_test_module(m)]


runtime_pkgs = (
    "pydantic_ai",  # core agent framework (the selftest exercises its TestModel)
    "anthropic",
    "openai",
    "groq",
    "mistralai",
    "cohere",
    "google.genai",  # provider SDKs, imported lazily
    "greenlet",
    "sqlalchemy",  # SQLAlchemy async engine internals
)
for pkg in runtime_pkgs:
    pkg_datas, pkg_binaries, pkg_hidden = _collect(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# aiosqlite is the sqlite+aiosqlite DBAPI driver SQLAlchemy loads by name.
hiddenimports += [m for m in collect_submodules("aiosqlite") if not _is_test_module(m)]

# pydantic-ai and some deps (e.g. genai_prices) read their own version via
# importlib.metadata at import, which needs the .dist-info metadata bundled.
datas += copy_metadata("pydantic_ai", recursive=True)

a = Analysis(
    [os.path.join(DESKTOP, "run.py")],
    pathex=[DESKTOP],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "google.genai.tests"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821 -- PYZ is a PyInstaller global

exe = EXE(  # noqa: F821 -- EXE is a PyInstaller global
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="quorum-gatherer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(  # noqa: F821 -- COLLECT is a PyInstaller global
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="quorum-gatherer",
)

# macOS-only; PyInstaller ignores BUNDLE on Windows/Linux.
app = BUNDLE(  # noqa: F821 -- BUNDLE is a PyInstaller global
    coll,
    name="quorum-gatherer.app",
    icon=None,
    bundle_identifier="com.brettbergin.quorum-gatherer",
)
