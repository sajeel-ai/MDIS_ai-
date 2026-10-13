"""Deterministic extraction with an explicitly opt-in LLM fallback."""

from app.config import settings
from app.providers.extraction.base import BaseExtractionProvider, ExtractionResult
from app.providers.extraction.local import LocalExtractionProvider
from app.providers.extraction.openai import OpenAIExtractionProvider


class HybridExtractionProvider(BaseExtractionProvider):
    """Use local deterministic extraction first; call OpenAI only when enabled."""

    def __init__(self) -> None:
        self.local = LocalExtractionProvider()
        self.llm = OpenAIExtractionProvider()

    async def extract_clinical_entities(self, text: str) -> ExtractionResult:
        result = await self.local.extract_clinical_entities(text)
        if result["entities"] or not settings.extraction_llm_fallback_enabled:
            return result
        fallback = await self.llm.extract_clinical_entities(text)
        fallback["raw_response"]["provider"] = "hybrid_llm_fallback"
        return fallback
