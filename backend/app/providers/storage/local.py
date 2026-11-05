"""Local File System Storage Provider with AES-256-GCM encryption at rest."""

import asyncio
from pathlib import Path

from app.config import settings
from app.providers.storage.base import BaseStorageProvider
from app.security.storage_crypto import decrypt_bytes, encrypt_bytes


class LocalStorageProvider(BaseStorageProvider):
    def __init__(self, base_path: str | None = None):
        self.base_path = base_path or settings.storage_local_path

    def _resolve_path(self, storage_key: str) -> Path:
        clean_key = (
            storage_key.removeprefix("local:")
            if storage_key.startswith("local:")
            else storage_key
        )
        if not clean_key or Path(clean_key).is_absolute():
            raise ValueError("Storage key must be a non-empty relative path")

        root = Path(self.base_path).resolve()
        target = (root / clean_key).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("Storage key resolves outside the storage root") from exc
        return target

    async def save_file(self, storage_key: str, file_bytes: bytes) -> str:
        target_path = self._resolve_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        encrypted_bytes = encrypt_bytes(file_bytes)

        def _write():
            with target_path.open("wb") as f:
                f.write(encrypted_bytes)

        await asyncio.to_thread(_write)
        return f"local:{storage_key}"

    async def save_file_from_path(self, storage_key: str, source_path: str) -> str:
        target_path = self._resolve_path(storage_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        def _read_and_encrypt_write():
            with open(source_path, "rb") as sf:
                plain = sf.read()
            encrypted = encrypt_bytes(plain)
            with target_path.open("wb") as df:
                df.write(encrypted)

        await asyncio.to_thread(_read_and_encrypt_write)
        return f"local:{storage_key}"

    async def read_file(self, storage_key: str) -> bytes:
        target_path = self._resolve_path(storage_key)
        if not target_path.is_file():
            raise FileNotFoundError(f"Stored document file not found at {target_path}")

        def _read():
            with target_path.open("rb") as f:
                return f.read()

        raw_bytes = await asyncio.to_thread(_read)
        # Transparently decrypt if encrypted; returns plain bytes if unencrypted
        return decrypt_bytes(raw_bytes)

    async def delete_file(self, storage_key: str) -> bool:
        target_path = self._resolve_path(storage_key)
        if target_path.is_file():
            target_path.unlink()
            return True
        return False
