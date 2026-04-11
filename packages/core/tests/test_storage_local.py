"""Unit tests for storage_local.py (LocalFSBackend)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from storage_local import LocalFSBackend


def test_local_backend_creates_base_dir(tmp_path):
    """LocalFSBackend creates the base directory on init."""
    base = tmp_path / "mystore"
    backend = LocalFSBackend(base_dir=str(base))
    assert base.exists()
    assert base.is_dir()


def test_local_backend_uses_env_var(tmp_path, monkeypatch):
    """Uses SLIDESHERLOCK_DATA_DIR env var as base when no base_dir given."""
    env_dir = tmp_path / "env_store"
    monkeypatch.setenv("SLIDESHERLOCK_DATA_DIR", str(env_dir))

    backend = LocalFSBackend()
    assert backend.base == env_dir
    assert env_dir.exists()


def test_put_writes_file(tmp_path):
    """put() writes bytes to the correct path under base."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    result = backend.put("jobs/abc/render/deck.pdf", b"PDF_CONTENT", "application/pdf")

    dest = tmp_path / "jobs" / "abc" / "render" / "deck.pdf"
    assert dest.exists()
    assert dest.read_bytes() == b"PDF_CONTENT"
    assert "deck.pdf" in result


def test_put_returns_path_string(tmp_path):
    """put() returns the absolute file path as a string."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    result = backend.put("some/key.json", b"{}", "application/json")
    assert isinstance(result, str)
    assert os.path.exists(result)


def test_put_creates_nested_dirs(tmp_path):
    """put() creates parent directories if they don't exist."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    backend.put("a/b/c/d/file.txt", b"data")
    assert (tmp_path / "a" / "b" / "c" / "d" / "file.txt").exists()


def test_get_reads_file(tmp_path):
    """get() reads bytes back from a previously written file."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    backend.put("test/file.bin", b"\x00\x01\x02")
    result = backend.get("test/file.bin")
    assert result == b"\x00\x01\x02"


def test_get_raises_for_missing_key(tmp_path):
    """get() raises FileNotFoundError for a nonexistent key."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError, match="Object not found"):
        backend.get("does/not/exist.json")


def test_exists_returns_true_for_written_key(tmp_path):
    """exists() returns True after a file has been put."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    backend.put("present/file.txt", b"hello")
    assert backend.exists("present/file.txt") is True


def test_exists_returns_false_for_missing_key(tmp_path):
    """exists() returns False for a key that was never written."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    assert backend.exists("ghost/file.txt") is False


def test_delete_removes_file(tmp_path):
    """delete() removes the file and returns True."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    backend.put("deleteme.txt", b"data")
    result = backend.delete("deleteme.txt")
    assert result is True
    assert not (tmp_path / "deleteme.txt").exists()


def test_delete_returns_false_for_missing(tmp_path):
    """delete() returns False when key does not exist."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    result = backend.delete("nope.txt")
    assert result is False


def test_get_url_returns_file_uri(tmp_path):
    """get_url() returns a file:// URI."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    url = backend.get_url("some/path.json")
    assert url.startswith("file://")
    assert "some/path.json" in url


def test_put_overwrites_existing_file(tmp_path):
    """put() overwrites an existing file with new content."""
    backend = LocalFSBackend(base_dir=str(tmp_path))
    backend.put("overwrite.txt", b"original")
    backend.put("overwrite.txt", b"updated")
    assert backend.get("overwrite.txt") == b"updated"
