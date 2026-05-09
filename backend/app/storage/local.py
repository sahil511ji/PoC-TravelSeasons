from __future__ import annotations

import os
from pathlib import Path

from ..config import get_settings


class LocalDiskStorage:
    def __init__(self, root_dir: str, public_base_url: str) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_base_url = public_base_url.rstrip("/")

    def _path(self, key: str) -> Path:
        # disallow path traversal
        clean = key.lstrip("/").replace("..", "_")
        return self.root / clean

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    async def get_bytes(self, key: str) -> bytes:
        p = self._path(key)
        if not p.exists():
            raise FileNotFoundError(key)
        return p.read_bytes()

    def public_url(self, key: str) -> str:
        return f"{self.public_base_url}/storage/{key.lstrip('/')}"

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            try:
                os.remove(p)
            except OSError:
                pass


def make_local_storage() -> LocalDiskStorage:
    s = get_settings()
    return LocalDiskStorage(s.LOCAL_STORAGE_DIR, s.PUBLIC_BASE_URL)
