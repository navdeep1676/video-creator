from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import get_settings


class StorageBackend(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def absolute_path(self, key: str) -> Path: ...

    @abstractmethod
    def size(self, key: str) -> int: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str | Path | None = None):
        settings = get_settings()
        self.root = Path(root or settings.storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Prevent path traversal
        key = key.lstrip("/").replace("\\", "/")
        if ".." in key.split("/"):
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root)):
            raise ValueError("Invalid storage key")
        return path

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def absolute_path(self, key: str) -> Path:
        return self._path(key)

    def size(self, key: str) -> int:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else 0

    def copy_file(self, src: Path, key: str) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    def ensure_dir(self, key_prefix: str) -> Path:
        path = self._path(key_prefix.rstrip("/") + "/.keep")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.parent


def get_storage() -> LocalStorage:
    return LocalStorage()
