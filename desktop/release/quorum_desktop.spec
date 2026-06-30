# PyInstaller spec for the quorum-gatherer desktop app.
#
# Invoked from the desktop/ directory (see release.yml and ci.yml):
#     uv run pyinstaller release/quorum_desktop.spec --noconfirm
#
# Produces a onedir bundle "quorum-gatherer" in desktop/dist/ (used as-is on Windows),
# plus a quorum-gatherer.app on macOS — matching the paths release.yml packages.

import os

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

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

# Provider SDKs are imported lazily by pydantic-ai, so static analysis misses them.
# Pull each in whole (submodules + data + shared libs). anthropic/openai/google arrive as
# pydantic-ai dependencies and may be absent depending on installed extras — tolerate that.
for pkg in ("pydantic_ai", "anthropic", "openai", "groq", "mistralai", "cohere"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

# google-genai is published under a couple of import names across versions.
for pkg in ("google.genai", "google.generativeai"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

# SQLAlchemy loads its DBAPI driver dynamically by name (sqlite+aiosqlite), so the
# aiosqlite package isn't discovered by static analysis — pull it in explicitly.
hiddenimports += collect_submodules("aiosqlite")

a = Analysis(
    [os.path.join(DESKTOP, "run.py")],
    pathex=[DESKTOP],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
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
