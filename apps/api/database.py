"""
Database engine + session + OCP-compliant initializer registry.

Adding a new database dialect = register_db_initializer("name", fn).
No edits to init_db().
"""
from __future__ import annotations

import os
from typing import Callable, Dict

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://slidesherlock:slidesherlock@localhost:5433/slidesherlock",
)

# SQLite needs check_same_thread=False for FastAPI's threadpool
_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    # Auto-create parent directory for the SQLite file
    _db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if _db_path and _db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(_db_path)), exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Database initializer registry (OCP)
# ---------------------------------------------------------------------------

DBInitializer = Callable[[Engine], None]
_DB_INITIALIZER_REGISTRY: Dict[str, DBInitializer] = {}


def register_db_initializer(dialect: str, initializer: DBInitializer) -> None:
    """Register a startup initializer for a SQLAlchemy dialect.

    Adding a new database (e.g. mysql, duckdb) = one call here. init_db()
    never needs to change.
    """
    _DB_INITIALIZER_REGISTRY[dialect] = initializer


def init_db() -> None:
    """Run the registered initializer for the active engine's dialect.

    Unknown dialects are a no-op (assume the operator manages schema
    out-of-band, e.g. via their own migration tool).
    """
    initializer = _DB_INITIALIZER_REGISTRY.get(engine.dialect.name)
    if initializer is None:
        return
    initializer(engine)


# --- built-in initializers ------------------------------------------------


def _sqlite_init(engine_: Engine) -> None:
    """SQLite has no alembic support (existing migrations are Postgres DDL).

    Use SQLAlchemy's create_all — sufficient for the dialect-agnostic
    models in apps/api/models.py.
    """
    # Importing models registers them on Base.metadata.
    from . import models  # noqa: F401

    Base.metadata.create_all(engine_)


def _postgres_init(engine_: Engine) -> None:
    """Postgres schema is owned by alembic. Startup is a no-op."""
    return None


register_db_initializer("sqlite", _sqlite_init)
register_db_initializer("postgresql", _postgres_init)
