"""
Local filesystem storage backend. Implements the StorageBackend protocol.

Used when STORAGE_BACKEND=local. Stores files under SLIDESHERLOCK_DATA_DIR
(default: ~/.slidesherlock/data).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class LocalFSBackend:
    def __init__(self, base_dir: Optional[str] = None):
        base = (
            base_dir
            or os.environ.get("SLIDESHERLOCK_DATA_DIR")
            or os.path.expanduser("~/.slidesherlock/data")
        )
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.base / key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return str(path)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object not found: {key}")
        with open(path, "rb") as f:
            return f.read()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_url(self, key: str) -> str:
        return f"file://{self._path(key)}"


# Auto-register with the storage backend registry
try:
    from storage_backend import register_storage_backend

    register_storage_backend("local", LocalFSBackend)
except ImportError:
    pass
