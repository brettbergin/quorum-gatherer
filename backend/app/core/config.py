"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QUORUM_", extra="ignore")

    # Persistence
    database_url: str = "sqlite+aiosqlite:///./quorum.db"

    # When true, all agents run on pydantic-ai's TestModel (no provider keys / network).
    # Handy for clicking through the UI locally without configuring an LLM provider.
    use_test_model: bool = False

    # Where the agent definition files live (the dedicated, human-readable folder).
    agent_prompts_dir: Path = BACKEND_ROOT / "agent_prompts"

    # Fernet key used to encrypt provider API keys at rest. Generate one for prod:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # A deterministic dev default is derived in core.security when this is unset.
    encryption_key: str | None = None

    # CORS origins for the React dev server.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Fallback provider API keys (used when a user has not configured one in the UI).
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    mistral_api_key: str | None = None
    cohere_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
