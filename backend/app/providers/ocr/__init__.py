"""OCR Provider Factory."""

from app.config import settings
from app.providers.ocr.azure import AzureOCRProvider
from app.providers.ocr.base import BaseOCRProvider
from app.providers.ocr.local import LocalOCRProvider
from app.providers.ocr.mock import MockOCRProvider


def get_ocr_provider(provider_name: str | None = None) -> BaseOCRProvider:
    name = (provider_name or settings.ocr_provider).lower().strip()

    if name == "mock":
        return MockOCRProvider()

    if name == "local":
        return LocalOCRProvider()

    if name == "azure":
        return AzureOCRProvider()

    raise ValueError(
        f"Unsupported OCR provider: {name}. "
        "Expected one of: mock, local, azure."
    )
