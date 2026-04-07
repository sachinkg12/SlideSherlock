"""
Storage backend abstraction. MinIO (S3-compatible) is the default,
LocalFS is the simpler alternative for pip install / no-Docker setups.

Adding a new storage backend = register_storage_backend("name", Factory).
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    def put(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        ...

    def get(self, key: str) -> bytes:
        ...

    def exists(self, key: str) -> bool:
        ...

    def delete(self, key: str) -> bool:
        ...

    def get_url(self, key: str) -> str:
        ...


_STORAGE_REGISTRY: Dict[str, Callable[[], StorageBackend]] = {}


def _default_backend() -> str:
    """Pick a sensible storage default based on the configured database.

    SQLite users almost certainly don't have MinIO running, so pair them
    with the LocalFS backend automatically. Everything else gets MinIO.
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("sqlite"):
        return "local"
    return "minio"


def register_storage_backend(name: str, factory: Callable[[], StorageBackend]) -> None:
    """Register a storage backend factory by name."""
    _STORAGE_REGISTRY[name] = factory


def list_storage_backends() -> Dict[str, Callable[[], StorageBackend]]:
    return dict(_STORAGE_REGISTRY)


def get_storage_backend() -> StorageBackend:
    """Factory: returns configured storage backend. Default: minio.

    Controlled by STORAGE_BACKEND env var.
    """
    # Ensure built-in backends are registered (lazy import to avoid cycles)
    if "minio" not in _STORAGE_REGISTRY:
        try:
            import storage  # noqa: F401
        except Exception:
            pass
    if "local" not in _STORAGE_REGISTRY:
        try:
            import storage_local  # noqa: F401
        except Exception:
            pass

    backend_name = (
        (os.environ.get("STORAGE_BACKEND") or _default_backend()).strip().lower()
    )
    factory = _STORAGE_REGISTRY.get(backend_name)
    if not factory:
        raise ValueError(
            f"Unknown STORAGE_BACKEND: {backend_name}. "
            f"Available: {sorted(_STORAGE_REGISTRY.keys())}"
        )
    return factory()
