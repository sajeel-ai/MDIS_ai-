"""OCR Provider Base Interface."""

from abc import ABC, abstractmethod
from typing import TypedDict


class OCRPage(TypedDict, total=False):
    page_number: int
    text: str
    confidence: float | None
    method: str


class OCRResult(TypedDict, total=False):
    text: str
    confidence: float | None
    page_count: int
    engine: str
    engine_version: str
    pages: list[OCRPage]


class BaseOCRProvider(ABC):
    @abstractmethod
    async def extract_text(
        self,
        file_bytes: bytes,
        mime_type: str | None = None,
    ) -> OCRResult:
        """Extract text and metadata from document file bytes."""
        raise NotImplementedError
