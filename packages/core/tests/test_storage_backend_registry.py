"""
Tests for the OCP-compliant storage backend registry and SQLite/LocalFS
auto-pairing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import storage_backend  # noqa: E402
from storage_local import LocalFSBackend  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SLIDESHERLOCK_DATA_DIR", str(tmp_path / "data"))
    yield


def test_register_and_get_custom_backend(monkeypatch):
    """A new backend can be added with one register call — OCP."""

    class _Dummy:
        def put(self, key, data, content_type="application/octet-stream"):
            return key

        def get(self, key):
            return b""

        def exists(self, key):
            return False

        def delete(self, key):
            return False

        def get_url(self, key):
            return f"dummy://{key}"

    storage_backend.register_storage_backend("dummy", _Dummy)
    monkeypatch.setenv("STORAGE_BACKEND", "dummy")
    backend = storage_backend.get_storage_backend()
    assert isinstance(backend, _Dummy)


def test_default_backend_minio_when_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@localhost/z")
    assert storage_backend._default_backend() == "minio"


def test_default_backend_local_when_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./slidesherlock.db")
    assert storage_backend._default_backend() == "local"


def test_default_backend_minio_when_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert storage_backend._default_backend() == "minio"


def test_localfs_round_trip(tmp_path):
    backend = LocalFSBackend(base_dir=str(tmp_path))
    backend.put("foo/bar.txt", b"hello", "text/plain")
    assert backend.exists("foo/bar.txt")
    assert backend.get("foo/bar.txt") == b"hello"
    assert backend.get_url("foo/bar.txt").startswith("file://")
    assert backend.delete("foo/bar.txt") is True
    assert not backend.exists("foo/bar.txt")


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "nonexistent_backend_xyz")
    with pytest.raises(ValueError, match="Unknown STORAGE_BACKEND"):
        storage_backend.get_storage_backend()
