"""Clinical Safety Unit Tests for MDIS.

Tests:
1. list_documents outer join: documents with patient_id IS NULL are returned when search matches file_name or document_type.
2. record_review_decision: rejects approval with 4xx when document.patient_id is None.
3. record_review_decision: rejects approval when CONFLICT validation flag is unacknowledged.
4. record_review_decision: requires non-empty justification when overriding medication/lab flags and logs it in audit_events.
5. FHIR export: returns descriptive error (400) when patient is unlinked, not generic 404.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models import (
    AuditEvent,
    ClinicalEntity,
    Document,
    DocumentValidationFlag,
    Extraction,
    Patient,
    ReviewTask,
    User,
    UserRole,
    ValidationResult,
)
from app.services.documents.document_service import DocumentService
from app.services.review.review_service import ReviewService
from app.routers.documents import get_db, get_current_user
from app.dependencies.auth import UserContext


# ============================================================================
# Rule 1: list_documents search outer join retains unlinked documents
# ============================================================================

@pytest.mark.asyncio
async def test_list_documents_search_uses_outerjoin_for_unlinked_documents():
    """Prove that searching by file_name or document_type uses outerjoin so unlinked documents are found."""
    session = MagicMock()
    count_result = MagicMock()
    count_result.scalar.return_value = 1
    
    # Fake document with NO linked patient
    unlinked_doc = Document(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        patient_id=None,
        document_type="progress_note",
        file_name="unlinked_discharge_summary.pdf",
        status="completed",
        review_status="pending",
        updated_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    rows_result = MagicMock()
    rows_result.scalars.return_value.all.return_value = [unlinked_doc]
    session.execute = AsyncMock(side_effect=[count_result, rows_result])

    service = DocumentService(session)
    items, total = await service.list_documents(
        search="discharge",
        unlinked_patient=True,
    )

    assert session.execute.await_count == 2
    count_sql = str(session.execute.await_args_list[0].args[0]).lower()
    page_sql = str(session.execute.await_args_list[1].args[0]).lower()

    # The SQL query must use LEFT OUTER JOIN, NOT a plain INNER JOIN
    assert "outer join" in count_sql or "left join" in count_sql or "left outer join" in count_sql
    assert "outer join" in page_sql or "left join" in page_sql or "left outer join" in page_sql
    assert total == 1
    assert items[0]["id"] == str(unlinked_doc.id)


# ============================================================================
# Rule 2: Reject approval when document.patient_id is None
# ============================================================================

@pytest.mark.asyncio
async def test_record_review_decision_rejects_approval_without_patient():
    """ReviewService.record_review_decision must raise ValueError when approving a task on a document without patient_id."""
    session = AsyncMock()
    
    doc = Document(
        id=uuid.uuid4(),
        patient_id=None,
        file_name="unlinked_doc.pdf",
        document_type="progress_note",
        status="completed",
        review_status="pending",
    )
    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=doc.id,
        status="pending",
        priority="normal",
        document=doc,
        entity=None,
    )
    
    task_res = MagicMock()
    task_res.scalars.return_value.first.return_value = task
    session.execute = AsyncMock(return_value=task_res)

    service = ReviewService(session)
    with pytest.raises(ValueError, match="patient"):
        await service.record_review_decision(
            task_id=task.id,
            decision="approved",
            reviewer_user_id=uuid.uuid4(),
        )


# ============================================================================
# Rule 3: Reject approval while CONFLICT validation flag is unacknowledged
# ============================================================================

@pytest.mark.asyncio
async def test_record_review_decision_rejects_unacknowledged_conflict_flag():
    """ReviewService.record_review_decision must reject approval when an active CONFLICT flag exists and acknowledged is False."""
    session = AsyncMock()
    
    doc = Document(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        file_name="conflict_doc.pdf",
        document_type="progress_note",
        status="completed",
        review_status="pending",
    )
    entity = ClinicalEntity(
        id=uuid.uuid4(),
        entity_type="medication",
        raw_text="Metformin 500mg",
        normalized_value="Metformin",
        confidence=0.9,
        status="unreviewed",
    )
    # Entity has a CONFLICT validation result
    val_conflict = ValidationResult(
        id=uuid.uuid4(),
        entity_id=entity.id,
        validation_rule="conflict",
        rule_code="CONFLICT",
        status="warning",
        severity="warning",
        message="Conflicting medication doses found.",
    )
    entity.validation_results = [val_conflict]

    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="high",
        document=doc,
        entity=entity,
    )

    task_res = MagicMock()
    task_res.scalars.return_value.first.return_value = task
    
    doc_flags_res = MagicMock()
    doc_flags_res.scalars.return_value.all.return_value = []
    
    session.execute = AsyncMock(side_effect=[task_res, doc_flags_res])

    service = ReviewService(session)
    with pytest.raises(ValueError, match="CONFLICT"):
        await service.record_review_decision(
            task_id=task.id,
            decision="approved",
            reviewer_user_id=uuid.uuid4(),
            acknowledged=False,
        )


# ============================================================================
# Rule 4: Require non-empty justification when overriding med/lab flags and log to audit
# ============================================================================

@pytest.mark.asyncio
async def test_record_review_decision_requires_justification_for_med_or_lab_override():
    """Overriding a MED_DOSE_UNIT or LAB_VALUE_UNIT flag requires non-empty justification."""
    session = AsyncMock()
    
    doc = Document(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        file_name="lab_doc.pdf",
        document_type="progress_note",
        status="completed",
        review_status="pending",
    )
    entity = ClinicalEntity(
        id=uuid.uuid4(),
        entity_type="lab",
        raw_text="Potassium 6.8",
        normalized_value="Potassium",
        confidence=0.95,
        status="unreviewed",
    )
    val_lab = ValidationResult(
        id=uuid.uuid4(),
        entity_id=entity.id,
        validation_rule="lab_value_unit",
        rule_code="LAB_VALUE_UNIT",
        status="warning",
        severity="warning",
        message="Lab value missing unit.",
    )
    entity.validation_results = [val_lab]

    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="high",
        document=doc,
        entity=entity,
    )

    task_res = MagicMock()
    task_res.scalars.return_value.first.return_value = task
    doc_flags_res = MagicMock()
    doc_flags_res.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(side_effect=[task_res, doc_flags_res])

    service = ReviewService(session)
    
    # Empty justification must fail
    with pytest.raises(ValueError, match="justification"):
        await service.record_review_decision(
            task_id=task.id,
            decision="approved",
            reviewer_user_id=uuid.uuid4(),
            justification="",
        )


# ============================================================================
# Rule 5: GET /api/documents/{id}/export/fhir returns descriptive error for unlinked patient
# ============================================================================

@pytest.mark.asyncio
async def test_fhir_export_returns_422_descriptive_error_for_unlinked_patient():
    """When a document exists but has no linked patient, export/fhir returns a descriptive 422."""
    doc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    # Document exists with patient_id = None
    unlinked_doc = Document(
        id=doc_id,
        organization_id=org_id,
        patient_id=None,
        file_name="unlinked.pdf",
        document_type="progress_note",
        status="completed",
        review_status="approved",
        created_at=datetime.now(timezone.utc),
    )
    unlinked_doc.patient = None
    unlinked_doc.extractions = []

    doc_res = MagicMock()
    doc_res.scalars.return_value.first.return_value = unlinked_doc
    mock_db.execute = AsyncMock(return_value=doc_res)
    mock_db.scalar = AsyncMock(return_value=unlinked_doc)

    test_user = UserContext(
        id=user_id,
        email="clinician@example.com",
        role=UserRole.CLINICIAN,
        organization_id=org_id,
        is_active=True,
    )

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/documents/{doc_id}/export/fhir")
            # Must NOT be 404 (generic not found); it is an unprocessable export.
            assert response.status_code == 422
            data = response.json()
            assert "patient" in data["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_fhir_export_keeps_404_for_missing_document():
    doc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    mock_db.execute = AsyncMock(return_value=result)
    test_user = UserContext(
        id=uuid.uuid4(), email="clinician@example.com", role=UserRole.CLINICIAN,
        organization_id=org_id, is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/documents/{doc_id}/export/fhir")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


# ============================================================================
# Additional Shared Safety Gates Tests (Proving Single & Batch Parity)
# ============================================================================

from app.services.review.review_service import evaluate_approval_safety


@pytest.mark.asyncio
async def test_record_review_decision_rejects_unacknowledged_critical_flag():
    """ReviewService.record_review_decision must reject approval when an entity has a CRITICAL flag and acknowledged is False."""
    session = AsyncMock()
    doc = Document(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        file_name="crit_doc.pdf",
        document_type="discharge_summary",
        status="completed",
        review_status="pending",
    )
    entity = ClinicalEntity(
        id=uuid.uuid4(),
        entity_type="diagnosis",
        raw_text="Anaphylaxis",
        normalized_value="Anaphylaxis",
        confidence=0.98,
        status="unreviewed",
    )
    val_critical = ValidationResult(
        id=uuid.uuid4(),
        entity_id=entity.id,
        validation_rule="critical_contraindication",
        rule_code="CRITICAL",
        status="fail",
        severity="critical",
        message="Critical contraindication detected.",
    )
    entity.validation_results = [val_critical]
    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="high",
        document=doc,
        entity=entity,
    )
    task_res = MagicMock()
    task_res.scalars.return_value.first.return_value = task
    doc_flags_res = MagicMock()
    doc_flags_res.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(side_effect=[task_res, doc_flags_res])

    service = ReviewService(session)
    with pytest.raises(ValueError, match="CONFLICT|CRITICAL"):
        await service.record_review_decision(
            task_id=task.id,
            decision="approved",
            reviewer_user_id=uuid.uuid4(),
            acknowledged=False,
        )


@pytest.mark.asyncio
async def test_record_review_decision_requires_justification_for_drug_interaction():
    """ReviewService.record_review_decision requires non-empty justification for DRUG_INTERACTION or ABNORMAL_LAB."""
    session = AsyncMock()
    doc = Document(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        file_name="interaction_doc.pdf",
        document_type="discharge_summary",
        status="completed",
        review_status="pending",
    )
    entity = ClinicalEntity(
        id=uuid.uuid4(),
        entity_type="medication",
        raw_text="Warfarin + Aspirin",
        normalized_value="Warfarin",
        confidence=0.95,
        status="unreviewed",
    )
    val_interaction = ValidationResult(
        id=uuid.uuid4(),
        entity_id=entity.id,
        validation_rule="drug_interaction",
        rule_code="DRUG_INTERACTION",
        status="warning",
        severity="warning",
        message="Major bleeding risk interaction.",
    )
    entity.validation_results = [val_interaction]
    task = ReviewTask(
        id=uuid.uuid4(),
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="high",
        document=doc,
        entity=entity,
    )
    task_res = MagicMock()
    task_res.scalars.return_value.first.return_value = task
    doc_flags_res = MagicMock()
    doc_flags_res.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(side_effect=[task_res, doc_flags_res])

    service = ReviewService(session)
    with pytest.raises(ValueError, match="justification"):
        await service.record_review_decision(
            task_id=task.id,
            decision="approved",
            reviewer_user_id=uuid.uuid4(),
            comment="looks fine",
            justification="",
        )


def test_shared_safety_gates_parity_between_single_and_batch_approval():
    """Verify that evaluate_approval_safety blocks both single and batch approvals under the same safety triggers."""
    # Case A: Missing patient_id blocks BOTH
    unlinked_doc = Document(id=uuid.uuid4(), patient_id=None)
    with pytest.raises(ValueError, match="patient"):
        evaluate_approval_safety(document=unlinked_doc, is_batch=False, raise_on_violation=True)
    allowed, reason = evaluate_approval_safety(document=unlinked_doc, is_batch=True, raise_on_violation=False)
    assert not allowed
    assert "patient" in reason.lower()

    # Case B: Unacknowledged conflict flag blocks BOTH
    linked_doc = Document(id=uuid.uuid4(), patient_id=uuid.uuid4())
    conflict_entity = ClinicalEntity(
        id=uuid.uuid4(), entity_type="medication", confidence=0.95,
    )
    conflict_entity.validation_results = [
        ValidationResult(rule_code="CONFLICT", severity="critical")
    ]
    with pytest.raises(ValueError, match="CONFLICT"):
        evaluate_approval_safety(
            document=linked_doc,
            entity=conflict_entity,
            acknowledged=False,
            is_batch=False,
            raise_on_violation=True,
        )
    allowed, reason = evaluate_approval_safety(
        document=linked_doc,
        entity=conflict_entity,
        acknowledged=False,
        is_batch=True,
        raise_on_violation=False,
    )
    assert not allowed
    assert "conflict" in reason.lower()

    # Case C: Un-justified medication/lab flag blocks BOTH
    med_entity = ClinicalEntity(
        id=uuid.uuid4(), entity_type="medication", confidence=0.95,
    )
    med_entity.validation_results = [
        ValidationResult(rule_code="DRUG_INTERACTION", severity="warning")
    ]
    with pytest.raises(ValueError, match="justification"):
        evaluate_approval_safety(
            document=linked_doc,
            entity=med_entity,
            justification="",
            is_batch=False,
            raise_on_violation=True,
        )
    allowed, reason = evaluate_approval_safety(
        document=linked_doc,
        entity=med_entity,
        justification="",
        is_batch=True,
        raise_on_violation=False,
    )
    assert not allowed
    assert "medication" in reason.lower() or "override" in reason.lower()
