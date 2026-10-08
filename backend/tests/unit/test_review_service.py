"""Unit tests for ReviewService and Review Router APIs."""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db import get_db
from app.dependencies.auth import get_current_user
from app.services.review.review_service import ReviewService
from app.models import ReviewTask, Document, Patient, ClinicalEntity, EvidenceSpan, ValidationResult, DocumentVersion


@pytest.mark.asyncio
async def test_review_service_queue_formatting():
    mock_session = AsyncMock()

    # Create mock ORM objects
    doc_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    mock_patient = Patient(
        id=patient_id,
        first_name="Jane",
        last_name="Doe",
        mrn="MRN-TEST-99",
    )

    mock_doc = Document(
        id=doc_id,
        patient_id=patient_id,
        file_name="discharge_summary_jane.pdf",
        document_type="discharge_summary",
        created_at=datetime.now(timezone.utc),
    )
    mock_doc.patient = mock_patient

    mock_version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc_id,
        version_number=1,
        raw_text="Patient Jane Doe presents with chest pain and shortness of breath.",
    )
    mock_doc.versions = [mock_version]

    mock_entity = ClinicalEntity(
        id=entity_id,
        extraction_id=uuid.uuid4(),
        entity_type="diagnosis",
        raw_text="chest pain",
        normalized_value="Chest pain, unspecified",
        confidence=0.72,
        status="unreviewed",
    )

    mock_span = EvidenceSpan(
        id=uuid.uuid4(),
        entity_id=entity_id,
        document_version_id=mock_version.id,
        page_number=1,
        start_offset=27,
        end_offset=37,
        text="chest pain",
    )
    mock_entity.evidence_spans = [mock_span]

    mock_val = ValidationResult(
        id=uuid.uuid4(),
        entity_id=entity_id,
        validation_rule="CONFIDENCE_ABOVE_THRESHOLD",
        status="warning",
        message="Entity confidence below 0.85 threshold",
    )
    mock_entity.validation_results = [mock_val]

    task_id = uuid.uuid4()
    mock_task = ReviewTask(
        id=task_id,
        document_id=doc_id,
        entity_id=entity_id,
        priority="normal",
        reason="Human review required: confidence below threshold",
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    mock_task.document = mock_doc
    mock_task.entity = mock_entity

    # Mock count query scalar
    count_res = MagicMock()
    count_res.scalar.return_value = 1

    # Mock items query scalars
    items_res = MagicMock()
    items_res.scalars.return_value.all.return_value = [mock_task]

    mock_session.execute.side_effect = [count_res, items_res]

    service = ReviewService(mock_session)
    items, total = await service.get_review_queue(page=1, page_size=10, status="pending")

    assert total == 1
    assert len(items) == 1
    item = items[0]

    assert item["id"] == str(task_id)
    assert item["status"] == "pending"
    assert item["priority"] == "normal"
    assert item["document"]["file_name"] == "discharge_summary_jane.pdf"
    assert item["patient"]["display_name"] == "Jane Doe"
    assert item["patient"]["mrn"] == "MRN-TEST-99"
    assert item["entity"]["raw_text"] == "chest pain"
    assert item["entity"]["confidence"] == 0.72
    assert item["evidence"]["start_offset"] == 27
    assert item["validation"]["status"] == "warning"


@pytest.fixture(autouse=True)
def override_db_dependency():
    async def mock_get_db():
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_db] = mock_get_db

    async def mock_current_user():
        from app.models import User

        return User(
            id=uuid.uuid4(),
            email="reviewer@example.test",
            role="clinician",
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = mock_current_user
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_review_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        queue_res = await ac.get("/api/v1/review/queue")
        assert queue_res.status_code == 200
        data = queue_res.json()
        assert "items" in data
        assert "total" in data

        stats_res = await ac.get("/api/v1/review/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert "pending" in stats
        assert "high_priority" in stats
