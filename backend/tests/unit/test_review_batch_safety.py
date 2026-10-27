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

from app.models import ClinicalEntity, Document, ReviewTask, ValidationResult
from app.services.review.review_service import ReviewService


@pytest.mark.asyncio
async def test_batch_approve_rejects_document_without_linked_patient():
    session = AsyncMock()
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


@pytest.mark.asyncio
async def test_batch_approve_skips_low_confidence_entities():
    session = AsyncMock()
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

