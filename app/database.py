"""
DB engine/session setup — SQLite file, zero external services required.

Chosen specifically so this app deploys as a single Railway-free-tier
process: no separate MariaDB/Postgres/Redis containers to provision, unlike
the earlier Frappe-based version. Swapping to Postgres later (e.g. once on
a paid Railway plan) only means changing DATABASE_URL — everything above
this module is unaware of which DB engine is in use.
"""

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

# Lets a bare `uvicorn app.main:app --reload` (no shell env vars set by
# hand) pick up DATABASE_URL/etc. from a local .env file — the same file
# docker-compose.yml already reads for the Postgres+VPS path (Customer
# Request 2 Epic N). Deliberately NOT `dotenv.load_dotenv()`: that mutates
# the process-wide os.environ, which would leak DATABASE_URL into every
# other module that reads os.environ directly — including
# tests/conftest.py's Postgres-smoke-test opt-in, which relies on
# DATABASE_URL being absent by default so plain `pytest` stays on fast
# in-memory SQLite. `dotenv_values()` just returns a dict; nothing outside
# this module's own _env() lookups below is affected. No .env ships inside
# Docker images (see .dockerignore) or on Railway (env vars injected
# directly by the platform), so this is a no-op there either way.
_dotenv_values = dotenv_values()


def _env(key: str, default: str) -> str:
    return os.environ.get(key) or _dotenv_values.get(key) or default


DATA_DIR = Path(_env("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'umkm_omni.db'}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ---------------------------------------------------------------------------
# Lightweight schema migration — superseded by Alembic (app/migrations/) as
# of Customer Request 2 Epic N for the Postgres path, where schema changes
# are applied via `alembic upgrade head` before the app starts (see
# app/main.py's lifespan and Dockerfile's CMD). Kept here ONLY for the
# SQLite dev-mode fallback (DATABASE_URL starting with "sqlite"), so a local
# `uvicorn --reload` run against app/data/umkm_omni.db still auto-adds new
# columns without requiring Alembic for quick iteration.
#
# Base.metadata.create_all() only creates tables that don't exist yet; it
# never adds a new column to a table that was already created by an earlier
# version of this app. Without this, every time a model gains a field,
# users with an existing local umkm_omni.db would need to manually delete
# the file (which has already caused real confusion once). This runs a
# handful of `ALTER TABLE ... ADD COLUMN` statements for exactly the columns
# added after each table's first release, skipping any that already exist.
# New tables still just need create_all().
# ---------------------------------------------------------------------------

_COLUMN_MIGRATIONS = [
    # (table, column, ddl_type_and_default)
    ("platform", "fee_rate", "FLOAT DEFAULT 0"),
    ("product", "description", "TEXT DEFAULT ''"),
    ("product", "ppn_rate", "FLOAT DEFAULT 11.0"),
    ("product", "cogs_price", "FLOAT NOT NULL DEFAULT 0"),
    ("product", "unit_label", "VARCHAR NOT NULL DEFAULT 'Pcs'"),
    ("expense", "rule_no", "INTEGER NOT NULL DEFAULT 32"),
]

# Columns dropped from models after an earlier release — DBs created before
# the drop still have them (NOT NULL, no default), which breaks inserts that
# no longer supply a value. (table, column)
_COLUMN_DROPS = [
    ("account", "is_outlet_scoped"),  # leftover from the removed Outlet model
]


def run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, ddl in _COLUMN_MIGRATIONS:
            if table not in existing_tables:
                continue  # a fresh create_all() will already include this column
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))

        for table, column in _COLUMN_DROPS:
            if table not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table)}
            if column not in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))


def get_db():
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
