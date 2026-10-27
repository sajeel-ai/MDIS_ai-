"""Tests for hybrid provider timeout and error fallback — Item 6."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.extraction.base import ExtractionProviderFailure
from app.providers.extraction.hybrid import HybridExtractionProvider


def _local_result(entities=None, provider="local"):
    return {
        "entities": entities or [],
        "model_name": "local-clinical-extractor",
        "model_version": "v1.0",
        "raw_response": {"status": "success", "provider": provider, "entity_count": len(entities or [])},
    }


def _llm_result(entities=None):
    return {
        "entities": entities or [{"type": "diagnosis", "raw_text": "pneumonia"}],
        "model_name": "gpt-4o",
        "model_version": "2024-01",
        "raw_response": {"provider": "openai", "entity_count": 1},
    }


@pytest.fixture()
def provider():
    return HybridExtractionProvider()


@pytest.mark.asyncio
async def test_llm_timeout_returns_local_result(provider) -> None:
    """LLM times out → falls back to local result with correct provider tag."""
    with (
        patch.object(provider.local, "extract_clinical_entities", new=AsyncMock(return_value=_local_result())),
        patch.object(provider.llm, "extract_clinical_entities", new=AsyncMock(side_effect=asyncio.TimeoutError())),
        patch("app.providers.extraction.hybrid.settings") as mock_settings,
    ):
        mock_settings.extraction_llm_fallback_enabled = True
        result = await provider.extract_clinical_entities("test text")

    assert result["raw_response"]["provider"] == "hybrid_local_timeout_fallback"


@pytest.mark.asyncio
async def test_llm_rate_limit_returns_local_result(provider) -> None:
    """LLM raises ExtractionProviderFailure (e.g. 429) → falls back to local."""
    with (
        patch.object(provider.local, "extract_clinical_entities", new=AsyncMock(return_value=_local_result())),
        patch.object(
            provider.llm,
            "extract_clinical_entities",
            new=AsyncMock(side_effect=ExtractionProviderFailure("EXTRACTION_FAILED", "rate limited")),
        ),
        patch("app.providers.extraction.hybrid.settings") as mock_settings,
    ):
        mock_settings.extraction_llm_fallback_enabled = True
        result = await provider.extract_clinical_entities("test text")

    assert result["raw_response"]["provider"] == "hybrid_local_error_fallback"


@pytest.mark.asyncio
async def test_llm_success_returns_llm_result(provider) -> None:
    """Local returns no entities → LLM is called and its result is returned."""
    llm_res = _llm_result()
    with (
        patch.object(provider.local, "extract_clinical_entities", new=AsyncMock(return_value=_local_result(entities=[]))),
        patch.object(provider.llm, "extract_clinical_entities", new=AsyncMock(return_value=llm_res)),
        patch("app.providers.extraction.hybrid.settings") as mock_settings,
    ):
        mock_settings.extraction_llm_fallback_enabled = True
        result = await provider.extract_clinical_entities("test text")

    assert result["raw_response"]["provider"] == "hybrid_llm_fallback"


@pytest.mark.asyncio
async def test_local_has_entities_llm_never_called(provider) -> None:
    """Local returns entities → LLM is never invoked even when fallback is enabled."""
    entity = {"type": "diagnosis", "raw_text": "pneumonia"}
    local_res = _local_result(entities=[entity])
    llm_mock = AsyncMock(return_value=_llm_result())
    with (
        patch.object(provider.local, "extract_clinical_entities", new=AsyncMock(return_value=local_res)),
        patch.object(provider.llm, "extract_clinical_entities", new=llm_mock),
        patch("app.providers.extraction.hybrid.settings") as mock_settings,
    ):
        mock_settings.extraction_llm_fallback_enabled = True
        await provider.extract_clinical_entities("test text")

    llm_mock.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_disabled_llm_never_called(provider) -> None:
    """extraction_llm_fallback_enabled=False → LLM never called even when local is empty."""
    llm_mock = AsyncMock(return_value=_llm_result())
    with (
        patch.object(provider.local, "extract_clinical_entities", new=AsyncMock(return_value=_local_result(entities=[]))),
        patch.object(provider.llm, "extract_clinical_entities", new=llm_mock),
        patch("app.providers.extraction.hybrid.settings") as mock_settings,
    ):
        mock_settings.extraction_llm_fallback_enabled = False
        await provider.extract_clinical_entities("test text")

    llm_mock.assert_not_called()

