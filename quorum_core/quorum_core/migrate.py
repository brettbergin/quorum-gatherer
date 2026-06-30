"""Programmatic Alembic access so every app (web, desktop) applies the same migrations.

The desktop app calls `upgrade_to_head()` at startup (before the qasync loop starts) to
create/upgrade its local SQLite to the schema bundled with this quorum_core version.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from quorum_core.core.config import get_settings

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def make_alembic_config(database_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url or get_settings().database_url)
    return cfg


def upgrade_to_head(database_url: str | None = None) -> None:
    """Bring the database (default: settings.database_url) up to the latest migration."""
    command.upgrade(make_alembic_config(database_url), "head")
