"""Ensure misconfigured extraction cannot create a processing job."""

from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from app.config import settings
from app.providers.extraction import ExtractionProviderConfigurationError
from app.services.processing.job_service import JobService


@pytest.mark.asyncio
async def test_job_is_not_created_when_openai_key_is_missing(monkeypatch):
    monkeypatch.setattr(settings, "extraction_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    session = AsyncMock()
    document_result = MagicMock()
    document_result.scalars.return_value.first.return_value = MagicMock(
        id=uuid.uuid4(), status="uploaded"
    )
    no_job_result = MagicMock()
    no_job_result.scalars.return_value.first.return_value = None
    session.execute.side_effect = [document_result, no_job_result, no_job_result]

    with pytest.raises(ExtractionProviderConfigurationError, match="OPENAI_API_KEY"):
        await JobService(session).create_and_enqueue_job(uuid.uuid4())

    session.add.assert_not_called()
    session.commit.assert_not_awaited()
