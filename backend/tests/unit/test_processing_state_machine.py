"""Regression tests for separate processing and review lifecycles."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.models import ClinicalEntity, Document, ProcessingJob, ReviewTask, ValidationResult, AuditEvent
from app.services.processing.job_service import JobService
from app.services.review.review_service import ReviewService
from app.workflows.clinical_processing import ClinicalProcessingWorkflow
from app.workflows.states import aggregate_review_status


def _result(first=None, all_items=None):
    result = MagicMock()
    result.scalars.return_value.first.return_value = first
    result.scalars.return_value.all.return_value = [] if all_items is None else all_items
    return result


@pytest.mark.asyncio
async def test_step_failure_marks_step_job_and_document_failed():
    document_id = uuid.uuid4()
    job = ProcessingJob(id=uuid.uuid4(), document_id=document_id, status="queued")
    document = Document(
        id=document_id,
        patient_id=uuid.uuid4(),
        document_type="progress_note",
        source="test",
        status="queued",
        storage_key=None,
    )
    created_steps = []
    session = AsyncMock()
    session.add = Mock(side_effect=created_steps.append)
    session.execute.side_effect = [
        _result(first=job),
        _result(first=document),
        _result(all_items=created_steps),
    ]

    workflow = ClinicalProcessingWorkflow.__new__(ClinicalProcessingWorkflow)
    workflow.session = session
    workflow.ocr_provider = Mock()
    workflow.extraction_provider = Mock()
    workflow.storage_provider = Mock()

    with pytest.raises(RuntimeError, match="PROCESSING_INPUT_MISSING"):
        await workflow.execute_job(job.id)

    failed_step = next(step for step in created_steps if step.status == "failed")
    assert job.status == "failed"
    assert document.status == "failed"
    assert job.completed_at is not None
    assert failed_step.status == "failed"
    assert failed_step.error_code == "PROCESSING_INPUT_MISSING"
    assert failed_step.error_message
    assert failed_step.started_at is not None
    assert failed_step.completed_at is not None
    session.commit.assert_awaited()


def test_review_status_aggregation_uses_only_review_states():
    assert aggregate_review_status([]) == "not_required"
    assert aggregate_review_status(["pending"]) == "pending"
    assert aggregate_review_status(["pending", "in_review"]) == "in_review"
    assert aggregate_review_status(["approved", "rejected"]) == "rejected"


@pytest.mark.asyncio
async def test_processing_job_status_exposes_entity_warning_count():
    job = ProcessingJob(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        status="completed",
        pipeline_version="test",
        warning_count=2,
    )
    job.steps = []
    session = AsyncMock()
    session.execute.return_value = _result(first=job)
    result = await JobService(session).get_job_status(job.id)
    assert result["warning_count"] == 2
    assert aggregate_review_status(["approved", "corrected"]) == "approved"


@pytest.mark.asyncio
async def test_start_review_moves_only_the_review_lifecycle_to_in_review():
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        patient_id=uuid.uuid4(),
        document_type="progress_note",
        source="test",
        status="completed",
        review_status="pending",
    )
    document.versions = []
    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=document_id,
        priority="normal",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    task.document = document
    task.entity = None
    session = AsyncMock()
    session.execute.side_effect = [
        _result(first=task),
        _result(all_items=["in_review"]),
        _result(first=task),
    ]

    await ReviewService(session).start_review(task.id, reviewer_user_id=uuid.uuid4())

    assert task.status == "in_review"
    assert task.started_at is not None
    assert document.review_status == "in_review"
    assert document.status == "completed"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_review_decision_does_not_change_document_processing_status():
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        patient_id=uuid.uuid4(),
        document_type="progress_note",
        source="test",
        status="completed",
        review_status="pending",
    )
    document.versions = []
    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=document_id,
        priority="normal",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    task.document = document
    task.entity = None
    status_result = MagicMock()
    status_result.scalars.return_value.all.return_value = ["approved"]
    session = AsyncMock()
    session.execute.side_effect = [
        _result(first=task),
        _result(first=document),
        status_result,
        _result(first=task),
    ]
    session.add = Mock()

    await ReviewService(session).record_review_decision(task.id, "approved")

    assert document.status == "completed"
    assert document.review_status == "approved"
    assert task.status == "approved"


@pytest.mark.asyncio
async def test_correction_preserves_original_ai_value_and_records_decision_audit():
    document_id = uuid.uuid4()
    document = Document(
        id=document_id, patient_id=uuid.uuid4(), document_type="progress_note",
        source="test", status="completed", review_status="pending",
    )
    document.versions = []
    entity = ClinicalEntity(
        id=uuid.uuid4(), extraction_id=uuid.uuid4(), entity_type="diagnosis",
        raw_text="pneumonia", normalized_value="Pneumonia", confidence=.8,
        status="unreviewed", original_ai_value="Pneumonia",
    )
    entity.evidence_spans = []
    entity.validation_results = []
    task = ReviewTask(
        id=uuid.uuid4(), document_id=document_id, entity_id=entity.id,
        priority="normal", status="pending", created_at=datetime.now(timezone.utc),
    )
    task.document = document
    task.entity = entity
    status_result = _result(all_items=["corrected"])
    added = []
    session = AsyncMock()
    session.add = Mock(side_effect=added.append)
    session.execute.side_effect = [
        _result(first=task), _result(first=entity), _result(first=document),
        status_result, _result(first=task),
    ]

    await ReviewService(session).record_review_decision(
        task.id, "corrected", corrected_value="Lower respiratory infection",
    )

    assert entity.original_ai_value == "Pneumonia"
    assert entity.normalized_value == "Lower respiratory infection"
    assert task.completed_at is not None
    assert any(isinstance(event, AuditEvent) and event.action == "review_decision" for event in added)


@pytest.mark.asyncio
async def test_approve_clean_items_skips_entities_with_warnings():
    document_id = uuid.uuid4()
    document = Document(
        id=document_id, patient_id=uuid.uuid4(), document_type="progress_note",
        source="test", status="completed", review_status="pending",
    )
    clean_entity = ClinicalEntity(
        id=uuid.uuid4(), extraction_id=uuid.uuid4(), entity_type="diagnosis",
        raw_text="cough", normalized_value="Cough", confidence=.9, status="unreviewed",
    )
    clean_entity.validation_results = []
    flagged_entity = ClinicalEntity(
        id=uuid.uuid4(), extraction_id=uuid.uuid4(), entity_type="diagnosis",
        raw_text="fever", normalized_value="Fever", confidence=.9, status="unreviewed",
    )
    flagged_entity.validation_results = [ValidationResult(
        entity_id=flagged_entity.id, validation_rule="DATE_PLAUSIBLE",
        rule_code="DATE_PLAUSIBLE", status="warning", severity="warning",
    )]
    clean_task = ReviewTask(id=uuid.uuid4(), document_id=document_id, entity_id=clean_entity.id, priority="normal", status="pending")
    flagged_task = ReviewTask(id=uuid.uuid4(), document_id=document_id, entity_id=flagged_entity.id, priority="normal", status="pending")
    for task in (clean_task, flagged_task):
        task.document = document
    clean_task.entity = clean_entity
    flagged_task.entity = flagged_entity
    added = []
    session = AsyncMock()
    session.add = Mock(side_effect=added.append)
    session.execute.side_effect = [
        _result(all_items=[clean_task, flagged_task]),
        _result(all_items=["approved", "pending"]),
    ]

    count = await ReviewService(session).approve_clean_for_document(document_id)

    assert count == 1
    assert clean_task.status == "approved"
    assert clean_entity.status == "approved"
    assert flagged_task.status == "pending"
    assert flagged_entity.status == "unreviewed"
    assert any(isinstance(event, AuditEvent) and event.action == "approve_clean_review_items" for event in added)
