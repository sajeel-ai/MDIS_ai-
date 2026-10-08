"""Local File System Storage Provider."""

import asyncio
import os
import shutil
from app.config import settings
from app.providers.storage.base import BaseStorageProvider


class LocalStorageProvider(BaseStorageProvider):
    def __init__(self, base_path: str | None = None):
        self.base_path = base_path or settings.storage_local_path

    def _resolve_path(self, storage_key: str) -> str:
        # Strip scheme prefix like 'local:' if present
        clean_key = storage_key.split(":", 1)[-1] if ":" in storage_key else storage_key
        return os.path.abspath(os.path.join(self.base_path, clean_key))

    async def save_file(self, storage_key: str, file_bytes: bytes) -> str:
        target_path = self._resolve_path(storage_key)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        def _write():
            with open(target_path, "wb") as f:
                f.write(file_bytes)

        await asyncio.to_thread(_write)
        return f"local:{storage_key}"

    async def save_file_from_path(self, storage_key: str, source_path: str) -> str:
        target_path = self._resolve_path(storage_key)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source_path, target_path)
        return f"local:{storage_key}"

    async def read_file(self, storage_key: str) -> bytes:
        target_path = self._resolve_path(storage_key)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Stored document file not found at {target_path}")

        def _read():
            with open(target_path, "rb") as f:
                return f.read()

        return await asyncio.to_thread(_read)

    async def delete_file(self, storage_key: str) -> bool:
        target_path = self._resolve_path(storage_key)
        if os.path.exists(target_path):
            os.remove(target_path)
            return True
        return False
