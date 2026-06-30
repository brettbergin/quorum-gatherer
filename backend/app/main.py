"""FastAPI application entrypoint for the Product Strategy Council backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from quorum_core.core.config import get_settings
from quorum_core.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables for local/dev runs (Alembic manages real migrations).
    await init_db()
    # Load + validate agent definitions from agent_prompts/ so a bad file fails fast.
    from quorum_core.agents.loader import load_agents

    app.state.agents = load_agents()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Quorum Gatherer — Product Strategy Council", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Routers are registered here as they are implemented.
    from app.api import agents, chats, ws
    from app.api import settings as settings_api

    app.include_router(agents.router)
    app.include_router(chats.router)
    app.include_router(settings_api.router)
    app.include_router(ws.router)

    return app


app = create_app()
