"""Storage Provider Factory."""

from app.config import settings
from app.providers.storage.base import BaseStorageProvider
from app.providers.storage.local import LocalStorageProvider


def get_storage_provider(provider_name: str | None = None) -> BaseStorageProvider:
    return LocalStorageProvider()
