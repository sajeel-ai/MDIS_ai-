"""Extraction Provider Factory."""

from app.config import settings
from app.providers.extraction.base import BaseExtractionProvider
from app.providers.extraction.local import LocalExtractionProvider
from app.providers.extraction.mock import MockExtractionProvider
from app.providers.extraction.openai import OpenAIExtractionProvider

SUPPORTED_EXTRACTION_PROVIDERS = ("local", "mock", "openai")


class ExtractionProviderConfigurationError(RuntimeError):
    """Raised when the selected extraction provider cannot be used safely."""


def validate_extraction_provider_configuration(
    provider_name: str | None = None,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    name = (provider_name if provider_name is not None else settings.extraction_provider).strip().lower()

    if name not in SUPPORTED_EXTRACTION_PROVIDERS:
        expected = ", ".join(SUPPORTED_EXTRACTION_PROVIDERS)
        raise ExtractionProviderConfigurationError(
            f"Unsupported extraction provider. Expected one of: {expected}."
        )

    if name == "openai":
        resolved_key = settings.openai_api_key if api_key is None else api_key
        resolved_model = settings.openai_model if model is None else model
        if not resolved_key or not resolved_key.strip():
            raise ExtractionProviderConfigurationError(
                "OpenAI extraction requires OPENAI_API_KEY to be configured."
            )
        if not resolved_model or not resolved_model.strip():
            raise ExtractionProviderConfigurationError(
                "OpenAI extraction requires OPENAI_MODEL to be configured."
            )

    return name


def get_extraction_provider(
    provider_name: str | None = None,
) -> BaseExtractionProvider:
    name = validate_extraction_provider_configuration(provider_name)

    if name == "local":
        return LocalExtractionProvider()

    if name == "mock":
        return MockExtractionProvider()

    if name == "openai":
        return OpenAIExtractionProvider()

    raise AssertionError("Provider validation and factory selection are out of sync")
