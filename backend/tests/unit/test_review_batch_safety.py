"""Unit tests for Review batch approval safety gates.

Batch approval is permitted ONLY for items with:
1. No active validation flags (document-level and entity-level)
2. A linked patient record (document.patient_id is not None)
3. High confidence (entity.confidence >= review_confidence_threshold)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models import ClinicalEntity, ClinicalEntityRevision, Document, ReviewTask, ValidationResult
from app.services.review.review_service import ReviewService


@pytest.mark.asyncio
async def test_batch_approve_rejects_document_without_linked_patient():
    session = AsyncMock()
    added_events = []
    session.add = MagicMock(side_effect=added_events.append)
    service = ReviewService(session)

    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.patient_id = None  # Unlinked patient!
    mock_doc.organization_id = uuid.uuid4()

    mock_entity = MagicMock(spec=ClinicalEntity)
    mock_entity.confidence = 0.98
    mock_entity.validation_results = []

    mock_task = MagicMock(spec=ReviewTask)
    mock_task.id = uuid.uuid4()
    mock_task.document_id = doc_id
    mock_task.document = mock_doc
    mock_task.entity = mock_entity
    mock_task.status = "pending"

    # Mock DB query results
    mock_tasks_res = MagicMock()
    mock_tasks_res.scalars.return_value.all.return_value = [mock_task]

    mock_flags_res = MagicMock()
    mock_flags_res.scalars.return_value.first.return_value = None

    session.execute.side_effect = [mock_tasks_res, mock_flags_res]

    approved_count = await service.approve_clean_for_document(doc_id)
    assert approved_count == 0
    assert mock_task.status == "pending"
    from app.models import AuditEvent
    assert any(isinstance(event, AuditEvent) and event.action == "approve_clean_review_items" for event in added_events)


@pytest.mark.asyncio
async def test_batch_approve_skips_low_confidence_entities():
    session = AsyncMock()
    added_revisions = []
    session.add = MagicMock(side_effect=added_revisions.append)
    service = ReviewService(session)

    doc_id = uuid.uuid4()
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = doc_id
    mock_doc.patient_id = uuid.uuid4()  # Linked patient
    mock_doc.organization_id = uuid.uuid4()

    # Task 1: Low confidence (0.70 < 0.85)
    mock_entity_low = MagicMock(spec=ClinicalEntity)
    mock_entity_low.confidence = 0.70
    mock_entity_low.validation_results = []
    mock_task_low = MagicMock(spec=ReviewTask)
    mock_task_low.id = uuid.uuid4()
    mock_task_low.document_id = doc_id
    mock_task_low.document = mock_doc
    mock_task_low.entity = mock_entity_low
    mock_task_low.status = "pending"

    # Task 2: High confidence (0.95 >= 0.85)
    mock_entity_high = MagicMock(spec=ClinicalEntity)
    mock_entity_high.confidence = 0.95
    mock_entity_high.validation_results = []
    mock_task_high = MagicMock(spec=ReviewTask)
    mock_task_high.id = uuid.uuid4()
    mock_task_high.document_id = doc_id
    mock_task_high.document = mock_doc
    mock_task_high.entity = mock_entity_high
    mock_task_high.status = "pending"

    mock_tasks_res = MagicMock()
    mock_tasks_res.scalars.return_value.all.return_value = [mock_task_low, mock_task_high]

    mock_flags_res = MagicMock()
    mock_flags_res.scalars.return_value.first.return_value = None

    mock_statuses_res = MagicMock()
    mock_statuses_res.scalars.return_value.all.return_value = ["pending", "approved"]

    session.execute.side_effect = [mock_tasks_res, mock_flags_res, mock_statuses_res]

    with patch("app.services.review.review_service.record_audit_event", new=AsyncMock()):
        approved_count = await service.approve_clean_for_document(doc_id)
        # Only the high-confidence task was approved:
        assert approved_count == 1
        assert mock_task_low.status == "pending"
        assert mock_task_high.status == "approved"
        assert len(added_revisions) == 1
        assert isinstance(added_revisions[0], ClinicalEntityRevision)
        assert added_revisions[0].entity_id == mock_entity_high.id


def test_batch_gate_rejects_unavailable_confidence_and_reviewer_added_entities():
    from app.services.review.review_service import evaluate_approval_safety

    linked_document = MagicMock(spec=Document)
    linked_document.patient_id = uuid.uuid4()
    linked_document.validation_flags = []

    unavailable = MagicMock(spec=ClinicalEntity)
    unavailable.confidence = None
    unavailable.source = "ai_extracted"
    unavailable.validation_results = []
    allowed, reason = evaluate_approval_safety(
        document=linked_document,
        entity=unavailable,
        is_batch=True,
        min_confidence=0.85,
    )
    assert not allowed
    assert "confidence" in reason.lower()

    reviewer_added = MagicMock(spec=ClinicalEntity)
    reviewer_added.confidence = None
    reviewer_added.source = "reviewer_added"
    reviewer_added.validation_results = []
    allowed, reason = evaluate_approval_safety(
        document=linked_document,
        entity=reviewer_added,
        is_batch=True,
        min_confidence=0.85,
    )
    assert not allowed
    assert "reviewer-added" in reason.lower()

    # High confidence must not bypass the provenance-specific batch gate.
    reviewer_added.confidence = 0.98
    allowed, reason = evaluate_approval_safety(
        document=linked_document,
        entity=reviewer_added,
        is_batch=True,
        min_confidence=0.85,
    )
    assert not allowed
    assert "reviewer-added" in reason.lower()


def test_reviewer_added_entity_with_high_confidence_never_batch_approved():
    from app.services.review.review_service import evaluate_approval_safety

    document = MagicMock(spec=Document)
    document.patient_id = uuid.uuid4()
    document.validation_flags = []
    entity = MagicMock(spec=ClinicalEntity)
    entity.confidence = 0.98
    entity.source = "reviewer_added"
    entity.validation_results = []

    allowed, reason = evaluate_approval_safety(
        document=document,
        entity=entity,
        is_batch=True,
        min_confidence=0.85,
    )

    assert not allowed
    assert "reviewer-added" in reason.lower()


def test_single_and_batch_approval_gate_rejects_soft_deleted_patient():
    from app.services.review.review_service import evaluate_approval_safety

    document = MagicMock(spec=Document)
    document.patient_id = uuid.uuid4()
    document.validation_flags = []
    document.patient = MagicMock()
    document.patient.deleted_at = datetime.now(timezone.utc)
    for is_batch in (False, True):
        allowed, reason = evaluate_approval_safety(
            document=document, is_batch=is_batch, raise_on_violation=False,
        )
        assert not allowed
        assert "soft-deleted" in reason

