"""Mock LLM Extraction Provider for deterministic offline processing."""

from app.providers.extraction.local import LocalExtractionProvider


class MockExtractionProvider(LocalExtractionProvider):
    """Mock extraction provider leveraging deterministic local clinical extraction."""
    pass
