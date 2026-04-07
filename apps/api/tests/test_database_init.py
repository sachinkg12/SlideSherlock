"""
Tests for the OCP-compliant database initializer registry.
"""
from sqlalchemy import create_engine, inspect

from apps.api import database
from apps.api.database import (
    Base,
    _DB_INITIALIZER_REGISTRY,
    init_db,
    register_db_initializer,
)


def test_builtin_dialects_registered():
    assert "sqlite" in _DB_INITIALIZER_REGISTRY
    assert "postgresql" in _DB_INITIALIZER_REGISTRY


def test_register_custom_dialect_does_not_touch_init_db():
    """Adding a new dialect = one register call. init_db() unchanged."""
    called = {"v": False}

    def _mysql_init(_engine):
        called["v"] = True

    register_db_initializer("mysql", _mysql_init)
    assert _DB_INITIALIZER_REGISTRY["mysql"] is _mysql_init


def test_init_db_unknown_dialect_is_noop(monkeypatch):
    class _FakeDialect:
        name = "imaginary_db_2099"

    class _FakeEngine:
        dialect = _FakeDialect()

    monkeypatch.setattr(database, "engine", _FakeEngine())
    # Should not raise.
    init_db()


def test_sqlite_init_creates_tables(tmp_path, monkeypatch):
    """End-to-end: SQLite engine + _sqlite_init creates the schema."""
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    database._sqlite_init(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    # All ORM tables should exist.
    expected = {
        "projects",
        "jobs",
        "artifacts",
        "slides",
        "sources",
        "evidence_items",
        "source_refs",
        "claim_links",
        "entity_links",
    }
    assert expected.issubset(tables)
    # Sanity: Base.metadata picked up models on import.
    assert "projects" in Base.metadata.tables
