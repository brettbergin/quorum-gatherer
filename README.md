# quorum-gatherer

A **Product Strategy Council** as an application. Instead of pasting one giant prompt
into ChatGPT, you start a chat where a panel of expert agents "joins," each works your
idea independently **in its own isolated context window**, and a **Chairman** synthesizes
their perspectives into a single, decision-grade recommendation — all streamed live and
shown transparently.

## What's inside

- **8 council members + a Chairman**, each defined as a file in
  [`backend/agent_prompts/`](backend/agent_prompts) (YAML frontmatter + prompt body),
  sharing a common `_charter.md` prefix. Edit a file → change an agent.
- **pydantic-ai** drives each agent in its own context (no cross-agent leakage).
- **FastAPI** JSON API + **WebSocket** streaming of every agent's deliberation.
- **SQLAlchemy + SQLite** persistence.
- **React + TypeScript (Vite)** chat UI with per-agent panels and the Chairman's report.
- **Any LLM provider** (Anthropic, OpenAI, …) configurable from the UI.

## Architecture

```
backend/   FastAPI + pydantic-ai + SQLAlchemy
  app/
    core/          config, db, event bus, encryption
    models/        SQLAlchemy ORM
    schemas/       Pydantic request/response + structured agent outputs
    agents/        definition loader, provider factory, runner, orchestrator, synthesis
    api/           REST routers + WebSocket
  agent_prompts/   the 9 agent definition files (+ shared _charter.md)
frontend/  React + TypeScript (Vite)
```

The pipeline runs in two phases: **(A)** the 8 members deliberate concurrently and stream
their perspectives; **(B)** the Chairman synthesizes the final report in a fixed output
format, surfacing the council's tensions and trade-offs.

## Quickstart

```bash
make install        # uv sync backend + npm install frontend
make migrate        # create the SQLite schema
make dev-backend    # FastAPI on :8000
make dev-frontend   # Vite on :5173  (separate terminal)
```

Run `make help` for all tasks (lint, format, test, …). Configure provider API keys in the
UI Settings dialog, or via `backend/.env` (see `backend/.env.example`).

## Development

- `make lint` / `make format` — Ruff lint & format
- `make test` — pytest
- `make check` — what CI runs (format check + tests)
