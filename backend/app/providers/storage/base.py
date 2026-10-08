"""Storage Provider Base Interface."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseStorageProvider(ABC):
    @abstractmethod
    async def save_file(self, storage_key: str, file_bytes: bytes) -> str:
        """Save file bytes and return storage location string."""
        pass

    async def save_file_from_path(self, storage_key: str, source_path: str | Path) -> str:
        """Store a staged upload without loading it into memory."""
        raise NotImplementedError("This storage provider does not support staged uploads")

    @abstractmethod
    async def read_file(self, storage_key: str) -> bytes:
        """Read file bytes from storage key location."""
        pass

    @abstractmethod
    async def delete_file(self, storage_key: str) -> bool:
        """Delete stored file if it exists."""
        pass
