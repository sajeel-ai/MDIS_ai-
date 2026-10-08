"""Azure Document Intelligence OCR provider with fail-closed polling."""

import asyncio
import logging
from urllib.parse import urlsplit

from app.config import settings
from app.providers.ocr.base import BaseOCRProvider, OCRResult

logger = logging.getLogger(__name__)


def _word_confidences(page: dict) -> list[float]:
    return [
        float(word["confidence"])
        for word in page.get("words", [])
        if isinstance(word.get("confidence"), (int, float))
        and 0 <= float(word["confidence"]) <= 1
    ]


class AzureOCRProvider(BaseOCRProvider):
    def __init__(self, endpoint: str | None = None, key: str | None = None):
        self.endpoint = endpoint or settings.azure_doc_intel_endpoint
        self.key = key or settings.azure_doc_intel_key

    async def extract_text(self, file_bytes: bytes, mime_type: str | None = None) -> OCRResult:
        if not self.endpoint or not self.key:
            raise RuntimeError("AZURE_OCR_CONFIG_ERROR: provider endpoint or key is missing")

        try:
            import httpx

            endpoint = self.endpoint.rstrip("/")
            endpoint_parts = urlsplit(endpoint)
            if endpoint_parts.scheme not in {"https", "http"} or not endpoint_parts.netloc:
                raise ValueError("Invalid provider endpoint")
            headers = {
                "Ocp-Apim-Subscription-Key": self.key,
                "Content-Type": mime_type or "application/pdf",
            }
            analyze_url = f"{endpoint}/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2023-07-31"
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(analyze_url, headers=headers, content=file_bytes)
                response.raise_for_status()
                operation_url = response.headers.get("Operation-Location")
                result = response.json()

                if operation_url:
                    operation_parts = urlsplit(operation_url)
                    if (operation_parts.scheme, operation_parts.netloc) != (
                        endpoint_parts.scheme,
                        endpoint_parts.netloc,
                    ):
                        raise ValueError("Provider operation URL did not match configured endpoint")

                    async with asyncio.timeout(60):
                        for _ in range(60):
                            status_value = str(result.get("status", "")).casefold()
                            if status_value == "succeeded":
                                break
                            if status_value == "failed":
                                raise RuntimeError("Provider analysis failed")
                            await asyncio.sleep(1)
                            poll = await client.get(operation_url, headers=headers)
                            poll.raise_for_status()
                            result = poll.json()
                        else:
                            raise TimeoutError("Provider operation timed out")

            analysis = result.get("analyzeResult") or {}
            text = analysis.get("content")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Provider returned no recognized text")
            pages = analysis.get("pages") or []
            word_confidences = [value for page in pages for value in _word_confidences(page)]
            page_results = [
                {
                    "page_number": int(page.get("pageNumber", index)),
                    "text": " ".join(
                        line.get("content", "") for line in page.get("lines", [])
                    ),
                    "confidence": (
                        sum(_word_confidences(page)) / len(_word_confidences(page))
                        if _word_confidences(page)
                        else None
                    ),
                }
                for index, page in enumerate(pages, start=1)
            ]
            return OCRResult(
                text=text,
                confidence=(sum(word_confidences) / len(word_confidences)) if word_confidences else None,
                page_count=len(pages) or 1,
                engine="azure_doc_intelligence",
                pages=page_results,
            )
        except Exception as exc:
            logger.error("Azure OCR provider failed error_type=%s", type(exc).__name__)
            raise RuntimeError("OCR_FAILED: Azure Document Intelligence request failed") from None
