"""Tests for duplicate-safe processing requests and explicit retries."""

import uuid
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.models import Document, ProcessingJob
from app.services.processing.job_service import (
    JobService,
    ProcessingConflictError,
)
from app.workflows.clinical_processing import ClinicalProcessingWorkflow


def _document(status="uploaded"):
    return Document(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        document_type="progress_note",
        source="test",
        status=status,
    )


@pytest.mark.asyncio
async def test_first_processing_request_creates_one_job(monkeypatch):
    monkeypatch.setattr(
        "app.services.processing.job_service.validate_extraction_provider_configuration",
        Mock(),
    )
    document = _document()
    session = AsyncMock()
    session.add = Mock()
    service = JobService(session)
    service._get_document_for_update = AsyncMock(return_value=document)
    service._get_active_job = AsyncMock(return_value=None)
    service._get_latest_job = AsyncMock(return_value=None)

    result = await service.create_and_enqueue_job(document.id)

    assert result.created is True
    assert result.job.document_id == document.id
    assert result.job.status == "queued"
    assert document.status == "queued"
    session.add.assert_called_once_with(result.job)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_processing_request_returns_active_job_without_duplicate(monkeypatch):
    monkeypatch.setattr(
        "app.services.processing.job_service.validate_extraction_provider_configuration",
        Mock(),
    )
    document = _document("queued")
    active_job = ProcessingJob(
        id=uuid.uuid4(), document_id=document.id, status="queued"
    )
    session = AsyncMock()
    session.add = Mock()
    service = JobService(session)
    service._get_document_for_update = AsyncMock(return_value=document)
    service._get_active_job = AsyncMock(return_value=active_job)

    result = await service.create_and_enqueue_job(document.id)

    assert result.created is False
    assert result.job is active_job
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_document_does_not_create_another_job(monkeypatch):
    monkeypatch.setattr(
        "app.services.processing.job_service.validate_extraction_provider_configuration",
        Mock(),
    )
    document = _document("completed")
    completed_job = ProcessingJob(
        id=uuid.uuid4(), document_id=document.id, status="completed"
    )
    session = AsyncMock()
    session.add = Mock()
    service = JobService(session)
    service._get_document_for_update = AsyncMock(return_value=document)
    service._get_active_job = AsyncMock(return_value=None)
    service._get_latest_job = AsyncMock(return_value=completed_job)

    result = await service.create_and_enqueue_job(document.id)

    assert result.created is False
    assert result.job is completed_job
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_retry_creates_new_job_and_cleans_failed_job_outputs(monkeypatch):
    monkeypatch.setattr(
        "app.services.processing.job_service.validate_extraction_provider_configuration",
        Mock(),
    )
    document = _document("failed")
    failed_job = ProcessingJob(
        id=uuid.uuid4(), document_id=document.id, status="failed"
    )
    session = AsyncMock()
    session.add = Mock()
    service = JobService(session)
    service._get_document_for_update = AsyncMock(return_value=document)
    service._get_active_job = AsyncMock(return_value=None)
    service._get_latest_job = AsyncMock(return_value=failed_job)

    result = await service.retry_failed_job(document.id)

    assert result.created is True
    assert result.job.status == "queued"
    assert document.status == "queued"
    assert session.execute.await_count == 5
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_retry_rejects_completed_job(monkeypatch):
    document = _document("completed")
    completed_job = ProcessingJob(
        id=uuid.uuid4(), document_id=document.id, status="completed"
    )
    service = JobService(AsyncMock())
    service._get_document_for_update = AsyncMock(return_value=document)
    service._get_active_job = AsyncMock(return_value=None)
    service._get_latest_job = AsyncMock(return_value=completed_job)

    with pytest.raises(ProcessingConflictError, match="Only a failed or cancelled"):
        await service.retry_failed_job(document.id)


@pytest.mark.asyncio
async def test_duplicate_workflow_delivery_does_not_rerun_completed_job():
    completed_job = ProcessingJob(
        id=uuid.uuid4(), document_id=uuid.uuid4(), status="completed"
    )
    result = MagicMock()
    result.scalars.return_value.first.return_value = completed_job
    session = AsyncMock()
    session.execute.return_value = result
    workflow = ClinicalProcessingWorkflow.__new__(ClinicalProcessingWorkflow)
    workflow.session = session

    returned_job = await workflow.execute_job(completed_job.id)

    assert returned_job is completed_job
    session.commit.assert_not_awaited()
