# quorum-gatherer

![Coverage](https://raw.githubusercontent.com/brettbergin/quorum-gatherer/python-coverage-comment-action-data/badge.svg)

A **Product Strategy Council** as a native desktop app. Instead of pasting one giant prompt
into ChatGPT, you start a chat where a panel of expert agents "joins," each works your idea
independently **in its own isolated context window**, and a **Chairman** synthesizes their
perspectives into a single, decision-grade recommendation — all streamed live and shown
transparently.

It ships as a fully standalone, self-updating **desktop app for macOS + Windows**, built on a
shared `quorum_core` engine.

## What's inside

- **8 council members + a Chairman**, each defined as a file in
  [`quorum_core/quorum_core/agent_prompts/`](quorum_core/quorum_core/agent_prompts)
  (YAML frontmatter + prompt body), sharing a common `_charter.md` prefix.
- **pydantic-ai** drives each agent in its own context (no cross-agent leakage).
- **`quorum_core`** — one shared package (data model + council engine + migrations) that the
  desktop app imports. Single source of truth for the schema.
- **Desktop:** native PySide6 (Qt) thick-client running the engine in-process against its own
  local SQLite, with **self-update** (tufup) — heartbeat check, background download,
  auto-install + restart.
- **Any LLM provider** (Anthropic, OpenAI, Google, Groq, Mistral, Cohere) configurable from
  the UI; keys validated with a real call and encrypted at rest.

## Architecture (uv workspace)

```
quorum_core/         shared library — the source of truth
  quorum_core/
    core/            config, db, event bus, encryption
    models/          SQLAlchemy ORM
    schemas/         structured agent outputs
    agents/          loader, provider factory, runner, orchestrator, synthesis, validation
    services/        settings + users
    migrations/      Alembic (shipped with the app)
    agent_prompts/   the 9 agent definition files (+ shared _charter.md)
desktop/             PySide6 thick-client (one codebase -> macOS + Windows)
  quorum_desktop/    app, paths, engine, bridge (event_bus->Qt), updater, widgets/
  release/           PyInstaller spec + Inno Setup installer + TUF release tooling
```

The pipeline runs in two phases: **(A)** the 8 members deliberate concurrently and stream their
perspectives over an in-process event bus (bridged to Qt signals); **(B)** the Chairman
synthesizes the final report in a fixed output format.

## Run from source

```bash
make install                              # uv sync the workspace
make dev-desktop                          # run the native app (dev)
QUORUM_USE_TEST_MODEL=1 make dev-desktop  # demo without any provider key
```

Build a standalone bundle (produces `.app`/`.dmg` on macOS, an installer + onedir on Windows):

```bash
cd desktop && uv run pyinstaller release/quorum_desktop.spec --noconfirm
```

The app stores its database + encryption key under the OS user-data dir and runs the bundled
Alembic migrations on launch. Releases are built and published by GitHub Actions on a `v*` tag
([`.github/workflows/release.yml`](.github/workflows/release.yml)): macOS Developer ID signing +
notarization (self-skips to an unsigned `.dmg` until the signing secrets are set), a Windows
Inno Setup installer, and a `SHA256SUMS.txt`. Auto-update (tufup) activates by initializing the
TUF repo (`desktop/release/tuf/repo_tool.py init`), committing the public root, and setting the
`TUF_KEYS` secret + `ENABLE_AUTOUPDATE` repo variable.

## Download & run

Grab the latest build from the [Releases](https://github.com/brettbergin/quorum-gatherer/releases) page.

**macOS** (`quorum-gatherer-<ver>-macos.dmg`) — open the `.dmg` and drag the app to Applications.
The release build is signed with a Developer ID and notarized by Apple, so it launches with no
Gatekeeper warning. *(If a build is unsigned — before the signing secrets are configured — macOS
says "unidentified developer"; right-click the app → **Open** → **Open** the first time.)*

**Windows** (`quorum-gatherer-<ver>-windows-setup.exe`) — run the installer (per-user, no admin
needed). The installer is currently **unsigned**, so SmartScreen shows "Windows protected your PC"
on first run → click **More info → Run anyway**. A portable `.zip` is also attached.

**Verify your download** against the published `SHA256SUMS.txt` on the release:

```bash
# macOS / Linux
shasum -a 256 quorum-gatherer-*-macos.dmg      # compare to SHA256SUMS.txt
```
```powershell
# Windows (PowerShell)
Get-FileHash .\quorum-gatherer-*-windows-setup.exe -Algorithm SHA256   # compare to SHA256SUMS.txt
```

## Development

- `make lint` / `make format` — Ruff lint & format (`quorum_core` + `desktop`)
- `make test` — pytest (`quorum_core` + `desktop`)
- `make test-cov` — tests with coverage (enforces the 70% gate)
- `make check` — what CI runs (format check + tests)
- `make help` — all tasks
