# PyInstaller spec for the quorum-gatherer desktop app.
#
# Invoked from the desktop/ directory (see release.yml and ci.yml):
#     uv run pyinstaller release/quorum_desktop.spec --noconfirm
#
# Produces a onedir bundle "quorum-gatherer" in desktop/dist/ (used as-is on Windows),
# plus a quorum-gatherer.app on macOS — matching the paths release.yml packages.

import os
import re
import sys
import tempfile

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

# SPECPATH is injected by PyInstaller and points at this file's directory
# (.../desktop/release), so paths resolve no matter the current working directory.
DESKTOP = os.path.dirname(SPECPATH)  # noqa: F821 -- SPECPATH is a PyInstaller global
ASSETS = os.path.join(SPECPATH, "assets")  # noqa: F821
IS_WINDOWS = sys.platform.startswith("win")

# App version — parsed from quorum_core/__init__.py (release.yml stamps it before building).
_init = os.path.join(DESKTOP, "..", "quorum_core", "quorum_core", "__init__.py")
VERSION = re.search(r'__version__ = "([^"]+)"', open(_init).read()).group(1)
# CFBundleVersion / build number: CI sets QUORUM_BUILD_NUMBER; fall back to the version.
BUILD = os.environ.get("QUORUM_BUILD_NUMBER", VERSION)


def _windows_version_file():
    """Render the committed VSVersionInfo template with the current version, to a temp file
    passed to EXE(version=...) so quorum-gatherer.exe carries File/Product version metadata."""
    tmpl = open(os.path.join(SPECPATH, "windows_version_info.txt")).read()  # noqa: F821
    parts = (VERSION.split(".") + ["0", "0", "0"])[:4]
    vtuple = ", ".join(str(int(p) if p.isdigit() else 0) for p in parts)
    text = tmpl.replace("@VERSION_TUPLE@", vtuple).replace("@VERSION@", VERSION)
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    f.write(text)
    f.close()
    return f.name


VERSION_FILE = _windows_version_file() if IS_WINDOWS else None

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
    icon=os.path.join(ASSETS, "icon.ico") if IS_WINDOWS else None,
    version=VERSION_FILE,
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
    icon=os.path.join(ASSETS, "icon.icns"),
    bundle_identifier="com.brettbergin.quorum-gatherer",
    version=VERSION,
    info_plist={
        "CFBundleName": "quorum-gatherer",
        "CFBundleDisplayName": "quorum-gatherer",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": BUILD,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHumanReadableCopyright": "© Brett Bergin",
    },
)
