# quorum-gatherer

![Coverage](https://raw.githubusercontent.com/brettbergin/quorum-gatherer/python-coverage-comment-action-data/badge.svg)

A **Product Strategy Council** as an application. Instead of pasting one giant prompt
into ChatGPT, you start a chat where a panel of expert agents "joins," each works your
idea independently **in its own isolated context window**, and a **Chairman** synthesizes
their perspectives into a single, decision-grade recommendation — all streamed live and
shown transparently.

It ships as a **web app** (FastAPI + React) and as **native desktop apps** (macOS +
Windows) that are fully standalone and self-updating. All three share one data model so
their schemas stay version-aligned.

## What's inside

- **8 council members + a Chairman**, each defined as a file in
  [`quorum_core/quorum_core/agent_prompts/`](quorum_core/quorum_core/agent_prompts)
  (YAML frontmatter + prompt body), sharing a common `_charter.md` prefix.
- **pydantic-ai** drives each agent in its own context (no cross-agent leakage).
- **`quorum_core`** — one shared package (data model + council engine + migrations) that
  the web backend and the desktop app both import. Single source of truth for the schema.
- **Web:** FastAPI JSON API + WebSocket streaming, React + TypeScript (Vite) UI.
- **Desktop:** native PySide6 (Qt) thick-client running the engine in-process against its
  own local SQLite, with **self-update** (tufup) — heartbeat check, background download,
  auto-install + restart.
- **Any LLM provider** (Anthropic, OpenAI, Google, Groq, Mistral, Cohere) configurable
  from the UI; keys validated with a real call and encrypted at rest.

## Architecture (uv workspace)

```
quorum_core/         shared library — the source of truth
  quorum_core/
    core/            config, db, event bus, encryption
    models/          SQLAlchemy ORM
    schemas/         structured agent outputs
    agents/          loader, provider factory, runner, orchestrator, synthesis, validation
    services/        settings + users
    migrations/      Alembic (shipped with every app)
    agent_prompts/   the 9 agent definition files (+ shared _charter.md)
backend/             FastAPI web shell over quorum_core (api/, main.py)
desktop/             PySide6 thick-client (one codebase -> macOS + Windows)
  quorum_desktop/    app, paths, engine, bridge (event_bus->Qt), updater, widgets/
  release/           PyInstaller spec + TUF release tooling
frontend/            React + TypeScript (Vite)
```

The pipeline runs in two phases: **(A)** the 8 members deliberate concurrently and stream
their perspectives; **(B)** the Chairman synthesizes the final report in a fixed output
format. The web app forwards engine events over a WebSocket; the desktop app subscribes to
the same in-process event bus — same engine, two transports.

## Quickstart (web)

```bash
make install        # uv sync the workspace + npm install frontend
make migrate        # create the backend's SQLite schema
make dev-backend    # FastAPI on :8000
make dev-frontend   # Vite on :5173  (separate terminal)
```

## Desktop app

```bash
make dev-desktop                       # run the native app (dev)
QUORUM_USE_TEST_MODEL=1 make dev-desktop  # demo without any provider key
```

Build a standalone bundle (produces `.app`/`.dmg` on macOS, `.exe` folder on Windows):

```bash
cd desktop && uv run pyinstaller release/quorum_desktop.spec --noconfirm
```

The desktop app stores its database + encryption key under the OS user-data dir and runs
the bundled Alembic migrations on launch. Releases are built and published by GitHub
Actions on a `v*` tag (`.github/workflows/release.yml`); auto-update is activated by
initializing the TUF repo (`desktop/release/tuf/repo_tool.py init`), committing the public
root, setting the `TUF_KEYS` secret, and the `ENABLE_AUTOUPDATE` repo variable.

## Development

- `make lint` / `make format` — Ruff lint & format (all Python packages)
- `make test` — pytest (`quorum_core` + `backend`)
- `make check` — what CI runs (format check + tests)
- `make help` — all tasks
