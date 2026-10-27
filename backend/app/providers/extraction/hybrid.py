"""Deterministic extraction with an explicitly opt-in LLM fallback."""

import asyncio
import logging

from app.config import settings
from app.providers.extraction.base import BaseExtractionProvider, ExtractionProviderFailure, ExtractionResult
from app.providers.extraction.local import LocalExtractionProvider
from app.providers.extraction.openai import OpenAIExtractionProvider

logger = logging.getLogger(__name__)


class HybridExtractionProvider(BaseExtractionProvider):
    """Use local deterministic extraction first; fall back to OpenAI when enabled.

    The LLM is only invoked when:
    - settings.extraction_llm_fallback_enabled is True, AND
    - The local provider returned no entities.

    If the LLM times out, hits a rate-limit (429), or returns a 5xx, the
    provider falls back silently to the local result rather than propagating
    the error to the caller.
    """

    # Seconds to wait for the OpenAI provider before cancelling and falling back.
    LLM_TIMEOUT_SECONDS: float = 25.0

    def __init__(self) -> None:
        self.local = LocalExtractionProvider()
        self.llm = OpenAIExtractionProvider()

    async def extract_clinical_entities(self, text: str) -> ExtractionResult:
        local_result = await self.local.extract_clinical_entities(text)
        if local_result["entities"] or not settings.extraction_llm_fallback_enabled:
            return local_result

        try:
            llm_result = await asyncio.wait_for(
                self.llm.extract_clinical_entities(text),
                timeout=self.LLM_TIMEOUT_SECONDS,
            )
            llm_result["raw_response"]["provider"] = "hybrid_llm_fallback"
            return llm_result
        except asyncio.TimeoutError:
            logger.warning(
                "HybridExtractionProvider: LLM call timed out after %.1fs; using local result",
                self.LLM_TIMEOUT_SECONDS,
            )
            local_result["raw_response"]["provider"] = "hybrid_local_timeout_fallback"
            return local_result
        except ExtractionProviderFailure as exc:
            logger.warning(
                "HybridExtractionProvider: LLM failed (%s); using local result",
                exc.args[0] if exc.args else "unknown",
            )
            local_result["raw_response"]["provider"] = "hybrid_local_error_fallback"
            return local_result
        except Exception:
            logger.exception("HybridExtractionProvider: unexpected LLM error; using local result")
            local_result["raw_response"]["provider"] = "hybrid_local_error_fallback"
            return local_result
