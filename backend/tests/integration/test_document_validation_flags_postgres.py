"""PostgreSQL integration tests for DocumentValidationFlag lifecycle.

Covers:
1. Zero-entity note stores a document-level flag.
2. Two missing vitals in one note produce two rows without error.
3. Active document-level flag blocks approve_clean_for_document.
4. Superseded flag does not block approve_clean_for_document.
5. Manual approval still works when an active document-level flag exists.
6. Reprocessing supersedes old flags and keeps historical records.
7. Cross-organization isolation ensures flags do not leak across tenants.
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy import delete, select, func

from app.db import AsyncSessionLocal, engine
from app.models import (
    AuditEvent,
    ClinicalEntity,
    Document,
    DocumentValidationFlag,
    DocumentVersion,
    EvidenceSpan,
    Extraction,
    Organization,
    Patient,
    ProcessingJob,
    ProcessingStep,
    ReviewTask,
    ValidationResult,
    User,
    UserRole,
)
from app.services.review.review_service import ReviewService
from app.services.documents.document_service import DocumentService
from app.services.validation.engine import validate_document_level_issues
from app.workflows.clinical_processing import ClinicalProcessingWorkflow
from app.services.retention.retention_service import RetentionPurgeService
from app.config import settings


@pytest_asyncio.fixture
async def pg_test_env():
    await engine.dispose(close=False)
    async with AsyncSessionLocal() as db:
        org_a = Organization(name=f"Test Org A {uuid.uuid4().hex[:6]}")
        org_b = Organization(name=f"Test Org B {uuid.uuid4().hex[:6]}")
        db.add_all([org_a, org_b])
        await db.flush()

        reviewer = User(
            email=f"reviewer-{uuid.uuid4()}@example.test",
            role=UserRole.REVIEWER,
            organization_id=org_a.id,
            is_active=True,
        )
        patient_a = Patient(
            external_patient_id=f"PAT-A-{uuid.uuid4().hex[:6]}",
            organization_id=org_a.id,
        )
        patient_b = Patient(
            external_patient_id=f"PAT-B-{uuid.uuid4().hex[:6]}",
            organization_id=org_b.id,
        )
        db.add_all([reviewer, patient_a, patient_b])
        await db.flush()

        doc_a = Document(
            patient_id=patient_a.id,
            organization_id=org_a.id,
            document_type="progress_note",
            source="synthetic",
            file_name="note_a.txt",
            mime_type="text/plain",
            status="completed",
            review_status="pending",
        )
        doc_b = Document(
            patient_id=patient_b.id,
            organization_id=org_b.id,
            document_type="progress_note",
            source="synthetic",
            file_name="note_b.txt",
            mime_type="text/plain",
            status="completed",
            review_status="pending",
        )
        db.add_all([doc_a, doc_b])
        await db.flush()

        # Capture IDs before yield — after rollback SQLAlchemy expires
        # all attributes so accessing .id would trigger a lazy-load outside
        # an async context (MissingGreenlet).
        doc_a_id = doc_a.id
        doc_b_id = doc_b.id
        patient_a_id = patient_a.id
        patient_b_id = patient_b.id
        reviewer_id = reviewer.id
        org_a_id = org_a.id
        org_b_id = org_b.id

        context = {
            "db": db,
            "org_a": org_a,
            "org_b": org_b,
            "reviewer": reviewer,
            "doc_a": doc_a,
            "doc_b": doc_b,
        }
        try:
            yield context
        finally:
            await db.rollback()
            try:
                await db.execute(delete(DocumentValidationFlag).where(DocumentValidationFlag.document_id.in_([doc_a_id, doc_b_id])))
                await db.execute(delete(ReviewTask).where(ReviewTask.document_id.in_([doc_a_id, doc_b_id])))
                await db.execute(delete(ClinicalEntity).where(ClinicalEntity.extraction_id.in_(
                    select(Extraction.id).where(Extraction.document_id.in_([doc_a_id, doc_b_id]))
                )))
                await db.execute(delete(Extraction).where(Extraction.document_id.in_([doc_a_id, doc_b_id])))
                await db.execute(delete(Document).where(Document.id.in_([doc_a_id, doc_b_id])))
                await db.execute(delete(Patient).where(Patient.id.in_([patient_a_id, patient_b_id])))
                await db.commit()
            except Exception:
                await db.rollback()

            # Attempt user & org cleanup; if append-only audit_events reference them, ignore FK restriction
            try:
                await db.execute(delete(User).where(User.id == reviewer_id))
                await db.execute(delete(Organization).where(Organization.id.in_([org_a_id, org_b_id])))
                await db.commit()
            except Exception:
                await db.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_pg_zero_entity_note_stores_flag(pg_test_env):
    """Zero-entity note stores a DocumentValidationFlag in the DB."""
    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    note_text = "BP not recorded. Patient resting comfortably."
    issues = validate_document_level_issues(note_text, [])
    assert len(issues) == 1
    assert issues[0].rule_code == "vital_mentioned_not_extracted"

    ext = Extraction(document_id=doc.id, status="completed")
    db.add(ext)
    await db.flush()

    for issue in issues:
        db.add(DocumentValidationFlag(
            document_id=doc.id,
            extraction_id=ext.id,
            rule_code=issue.rule_code,
            severity=issue.severity,
            status="warning",
            message=issue.message,
            details=issue.details,
        ))
    await db.commit()

    res = await db.execute(
        select(DocumentValidationFlag).where(
            DocumentValidationFlag.document_id == doc.id,
            DocumentValidationFlag.superseded_at.is_(None),
        )
    )
    flags = res.scalars().all()
    assert len(flags) == 1
    assert flags[0].rule_code == "vital_mentioned_not_extracted"
    assert flags[0].severity == "warning"
    assert flags[0].details["vital_term"] == "blood pressure"
    assert flags[0].extraction_id == ext.id


@pytest.mark.asyncio
async def test_pg_two_missing_vitals_give_two_rows(pg_test_env):
    """Two missing vitals produce two distinct DocumentValidationFlag rows without constraint violations."""
    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    note_text = "Vitals: BP not recorded. Temperature was not documented."
    issues = validate_document_level_issues(note_text, [])
    vital_terms = {i.details.get("vital_term") for i in issues}
    assert "blood pressure" in vital_terms
    assert "temperature" in vital_terms

    ext = Extraction(document_id=doc.id, status="completed")
    db.add(ext)
    await db.flush()

    for issue in issues:
        db.add(DocumentValidationFlag(
            document_id=doc.id,
            extraction_id=ext.id,
            rule_code=issue.rule_code,
            severity=issue.severity,
            status="warning",
            message=issue.message,
            details=issue.details,
        ))
    await db.commit()

    res = await db.execute(
        select(DocumentValidationFlag).where(
            DocumentValidationFlag.document_id == doc.id,
            DocumentValidationFlag.superseded_at.is_(None),
        )
    )
    rows = res.scalars().all()
    assert len(rows) >= 2


@pytest.mark.asyncio
async def test_pg_active_flag_blocks_approve_clean(pg_test_env):
    """An active warning-severity DocumentValidationFlag blocks approve_clean_for_document."""
    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    ext = Extraction(document_id=doc.id, status="completed")
    db.add(ext)
    await db.flush()

    entity = ClinicalEntity(
        extraction_id=ext.id,
        entity_type="symptom",
        raw_text="fatigue",
        normalized_value="Fatigue",
        confidence=0.98,
        status="unreviewed",
    )
    db.add(entity)
    await db.flush()

    task = ReviewTask(
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="normal",
        reason="Test clean task",
    )
    flag = DocumentValidationFlag(
        document_id=doc.id,
        extraction_id=ext.id,
        rule_code="vital_mentioned_not_extracted",
        severity="warning",
        status="warning",
        message="BP missing",
        details={"vital_term": "blood pressure"},
    )
    db.add_all([task, flag])
    await db.commit()

    approved_count = await ReviewService(db).approve_clean_for_document(doc.id)
    assert approved_count == 0

    await db.refresh(task)
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_pg_superseded_flag_does_not_block_approve_clean(pg_test_env):
    """A superseded DocumentValidationFlag does not block clean auto-approval."""
    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    ext = Extraction(document_id=doc.id, status="completed")
    db.add(ext)
    await db.flush()

    entity = ClinicalEntity(
        extraction_id=ext.id,
        entity_type="symptom",
        raw_text="cough",
        normalized_value="Cough",
        confidence=0.98,
        status="unreviewed",
    )
    db.add(entity)
    await db.flush()

    task = ReviewTask(
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="normal",
        reason="Test clean task",
    )
    old_flag = DocumentValidationFlag(
        document_id=doc.id,
        extraction_id=ext.id,
        rule_code="vital_mentioned_not_extracted",
        severity="warning",
        status="warning",
        message="BP missing (historical)",
        details={"vital_term": "blood pressure"},
        superseded_at=datetime.now(timezone.utc),
    )
    db.add_all([task, old_flag])
    await db.commit()

    approved_count = await ReviewService(db).approve_clean_for_document(doc.id)
    assert approved_count == 1

    await db.refresh(task)
    assert task.status == "approved"


@pytest.mark.asyncio
async def test_pg_manual_approval_still_works(pg_test_env):
    """Reviewer can manually approve a task even when an active document-level warning flag is present."""
    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]
    reviewer = pg_test_env["reviewer"]

    ext = Extraction(document_id=doc.id, status="completed")
    db.add(ext)
    await db.flush()

    entity = ClinicalEntity(
        extraction_id=ext.id,
        entity_type="symptom",
        raw_text="fever",
        normalized_value="Fever",
        confidence=0.95,
        status="unreviewed",
    )
    db.add(entity)
    await db.flush()

    task = ReviewTask(
        document_id=doc.id,
        entity_id=entity.id,
        status="pending",
        priority="normal",
    )
    flag = DocumentValidationFlag(
        document_id=doc.id,
        extraction_id=ext.id,
        rule_code="vital_mentioned_not_extracted",
        severity="warning",
        status="warning",
        message="BP missing",
        details={"vital_term": "blood pressure"},
    )
    db.add_all([task, flag])
    await db.commit()

    result = await ReviewService(db).record_review_decision(
        task_id=task.id,
        decision="approved",
        reviewer_user_id=reviewer.id,
    )
    assert result["status"] == "approved"

    await db.refresh(task)
    assert task.status == "approved"


async def _persist_drug_interaction_review_case(pg_test_env):
    db = pg_test_env["db"]
    document = pg_test_env["doc_a"]
    extraction = Extraction(document_id=document.id, status="completed")
    db.add(extraction)
    await db.flush()
    entity = ClinicalEntity(
        extraction_id=extraction.id,
        entity_type="medication",
        raw_text="warfarin with aspirin",
        normalized_value="warfarin",
        confidence=0.99,
        status="unreviewed",
        assertion="present",
    )
    db.add(entity)
    await db.flush()
    flag = ValidationResult(
        entity_id=entity.id,
        validation_rule="drug_interaction",
        rule_code="DRUG_INTERACTION",
        status="warning",
        severity="warning",
        message="Potential interaction",
    )
    task = ReviewTask(
        document_id=document.id,
        entity_id=entity.id,
        status="pending",
        priority="high",
        document=document,
        entity=entity,
    )
    db.add_all([flag, task])
    await db.flush()
    return db, task.id, entity.id, flag.id, pg_test_env["reviewer"].id


@pytest.mark.asyncio
async def test_pg_override_requires_justification_without_state_change(pg_test_env):
    db, task_id, entity_id, _flag_id, actor_id = await _persist_drug_interaction_review_case(pg_test_env)
    with pytest.raises(ValueError, match="justification"):
        await ReviewService(db).record_review_decision(
            task_id=task_id,
            decision="approved",
            reviewer_user_id=actor_id,
            justification="   ",
        )
    task = await db.get(ReviewTask, task_id)
    entity = await db.get(ClinicalEntity, entity_id)
    assert task.status == "pending"
    assert task.decision is None
    assert entity.status == "unreviewed"
    assert await db.scalar(
        select(AuditEvent.id).where(AuditEvent.action == "review_decision", AuditEvent.resource_id == task_id)
    ) is None


@pytest.mark.asyncio
async def test_pg_override_audit_persists_actor_flag_justification_and_timestamp(pg_test_env):
    db, task_id, _entity_id, flag_id, actor_id = await _persist_drug_interaction_review_case(pg_test_env)
    justification = "Reviewed the interaction and confirmed an intentional monitored regimen."
    await ReviewService(db).record_review_decision(
        task_id=task_id,
        decision="approved",
        reviewer_user_id=actor_id,
        justification=justification,
    )
    event = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "review_decision",
            AuditEvent.resource_id == task_id,
            AuditEvent.user_id == actor_id,
        )
    )
    assert event is not None
    assert event.user_id == actor_id
    assert str(flag_id) in event.metadata_["override_flag_ids"]
    assert event.metadata_["justification"] == justification
    assert event.created_at is not None


@pytest.mark.asyncio
async def test_pg_scratchpad_purge_deletes_expired_jobs_and_preserves_audit(pg_test_env, monkeypatch):
    db = pg_test_env["db"]
    document = pg_test_env["doc_a"]
    monkeypatch.setattr(settings, "retention_scratchpad_days", 30)
    expired = ProcessingJob(
        document_id=document.id,
        pipeline_version="test",
        status="failed",
        created_at=datetime.now(timezone.utc) - timedelta(days=31),
    )
    recent = ProcessingJob(
        document_id=document.id,
        pipeline_version="test",
        status="cancelled",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add_all([expired, recent])
    await db.commit()
    expired_id, recent_id = expired.id, recent.id
    audit_count_before = await db.scalar(select(func.count()).select_from(AuditEvent))

    result = await RetentionPurgeService(db).run_retention_purge(dry_run=False)

    assert result["scratchpad_records_purged"] == 1
    assert await db.get(ProcessingJob, expired_id) is None
    assert await db.get(ProcessingJob, recent_id) is not None
    assert await db.scalar(select(func.count()).select_from(AuditEvent)) == audit_count_before


@pytest.mark.asyncio
async def test_pg_reprocess_supersedes_and_keeps_old_rows(pg_test_env):
    """Reprocessing marks previous flags as superseded while retaining them for history."""
    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    # Run 1
    ext1 = Extraction(document_id=doc.id, status="completed")
    db.add(ext1)
    await db.flush()
    flag1 = DocumentValidationFlag(
        document_id=doc.id,
        extraction_id=ext1.id,
        rule_code="vital_mentioned_not_extracted",
        severity="warning",
        status="warning",
        message="Run 1 missing BP",
        details={"vital_term": "blood pressure"},
    )
    db.add(flag1)
    await db.commit()

    # Run 2 (Simulating re-extraction Step 7 logic)
    ext2 = Extraction(document_id=doc.id, status="completed")
    db.add(ext2)
    await db.flush()

    now = datetime.now(timezone.utc)
    # Step 7 supersession query:
    from sqlalchemy import update
    await db.execute(
        update(DocumentValidationFlag)
        .where(
            DocumentValidationFlag.document_id == doc.id,
            DocumentValidationFlag.superseded_at.is_(None),
        )
        .values(superseded_at=now)
    )
    flag2 = DocumentValidationFlag(
        document_id=doc.id,
        extraction_id=ext2.id,
        rule_code="vital_mentioned_not_extracted",
        severity="warning",
        status="warning",
        message="Run 2 missing BP",
        details={"vital_term": "blood pressure"},
    )
    db.add(flag2)
    await db.commit()

    # Query all flags for this document
    res = await db.execute(
        select(DocumentValidationFlag)
        .where(DocumentValidationFlag.document_id == doc.id)
        .order_by(DocumentValidationFlag.created_at.asc())
    )
    all_flags = res.scalars().all()
    # >= 2 because the fixture is shared: other tests may have written flags
    # to doc_a already. We only guarantee at least 2 (one superseded, one active).
    assert len(all_flags) >= 2
    # The oldest flag must belong to ext1 and be superseded
    assert all_flags[0].extraction_id == ext1.id
    assert all_flags[0].superseded_at is not None
    assert all_flags[1].extraction_id == ext2.id
    assert all_flags[1].superseded_at is None


@pytest.mark.asyncio
async def test_pg_cross_org_isolation(pg_test_env):
    """Flags belonging to Org A do not affect approve_clean for Org B."""
    db = pg_test_env["db"]
    doc_a = pg_test_env["doc_a"]
    doc_b = pg_test_env["doc_b"]
    org_b = pg_test_env["org_b"]

    ext_a = Extraction(document_id=doc_a.id, status="completed")
    ext_b = Extraction(document_id=doc_b.id, status="completed")
    db.add_all([ext_a, ext_b])
    await db.flush()

    # Org A has an active warning flag
    flag_a = DocumentValidationFlag(
        document_id=doc_a.id,
        extraction_id=ext_a.id,
        rule_code="vital_mentioned_not_extracted",
        severity="warning",
        status="warning",
        message="Org A missing BP",
    )
    db.add(flag_a)

    # Org B has a clean entity and clean task
    entity_b = ClinicalEntity(
        extraction_id=ext_b.id,
        entity_type="symptom",
        raw_text="headache",
        normalized_value="Headache",
        confidence=0.99,
        status="unreviewed",
    )
    db.add(entity_b)
    await db.flush()

    task_b = ReviewTask(
        document_id=doc_b.id,
        entity_id=entity_b.id,
        status="pending",
        priority="normal",
    )
    db.add(task_b)
    await db.commit()

    approved_count_b = await ReviewService(db).approve_clean_for_document(
        document_id=doc_b.id,
        organization_id=org_b.id,
    )
    assert approved_count_b == 1

    await db.refresh(task_b)
    assert task_b.status == "approved"


@pytest.mark.asyncio
async def test_pg_workflow_zero_entity_note_stores_active_flag(pg_test_env, tmp_path):
    """Real ClinicalProcessingWorkflow execution on a zero-entity note with 'BP not recorded'.
    
    Proves that running the workflow through execute_job (the real pipeline path)
    unconditionally records exactly one active DocumentValidationFlag without anchor entities.
    """
    from app.providers.ocr.mock import MockOCRProvider
    from app.providers.extraction.local import LocalExtractionProvider
    from app.providers.storage.local import LocalStorageProvider

    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    note_text = "BP not recorded. Patient resting comfortably."
    storage = LocalStorageProvider(str(tmp_path / "storage"))
    storage_key = f"documents/{doc.id}/note.txt"
    await storage.save_file(storage_key, note_text.encode("utf-8"))

    doc.storage_key = storage_key
    doc.status = "uploaded"
    job = ProcessingJob(
        document_id=doc.id,
        status="queued",
        pipeline_version="test-pipeline",
    )
    db.add(job)
    await db.commit()

    workflow = ClinicalProcessingWorkflow(db)
    workflow.storage_provider = storage
    workflow.ocr_provider = MockOCRProvider()
    workflow.extraction_provider = LocalExtractionProvider()

    completed_job = await workflow.execute_job(job.id)
    assert completed_job.status == "completed"

    res = await db.execute(
        select(DocumentValidationFlag).where(
            DocumentValidationFlag.document_id == doc.id,
            DocumentValidationFlag.superseded_at.is_(None),
        )
    )
    flags = res.scalars().all()
    assert len(flags) == 1
    flag = flags[0]
    assert flag.rule_code == "vital_mentioned_not_extracted"
    assert flag.severity == "warning"
    assert flag.status == "warning"
    assert flag.details["vital_term"] == "blood pressure"
    assert flag.superseded_at is None


@pytest.mark.asyncio
async def test_pg_workflow_reprocess_supersedes_and_keeps_old_rows(pg_test_env, tmp_path):
    """Running ClinicalProcessingWorkflow twice for the same document supersedes the first flag and keeps both."""
    from app.providers.ocr.mock import MockOCRProvider
    from app.providers.extraction.local import LocalExtractionProvider
    from app.providers.storage.local import LocalStorageProvider

    db = pg_test_env["db"]
    doc = pg_test_env["doc_a"]

    note_text = "BP not recorded. Patient resting comfortably."
    storage = LocalStorageProvider(str(tmp_path / "storage"))
    storage_key = f"documents/{doc.id}/note.txt"
    await storage.save_file(storage_key, note_text.encode("utf-8"))

    doc.storage_key = storage_key
    doc.status = "uploaded"
    job1 = ProcessingJob(
        document_id=doc.id,
        status="queued",
        pipeline_version="test-pipeline",
    )
    db.add(job1)
    await db.commit()

    # First workflow execution
    wf1 = ClinicalProcessingWorkflow(db)
    wf1.storage_provider = storage
    wf1.ocr_provider = MockOCRProvider()
    wf1.extraction_provider = LocalExtractionProvider()
    await wf1.execute_job(job1.id)

    # Prepare second job (reprocessing)
    doc.status = "queued"
    job2 = ProcessingJob(
        document_id=doc.id,
        status="queued",
        pipeline_version="test-pipeline",
    )
    db.add(job2)
    await db.commit()

    # Second workflow execution
    wf2 = ClinicalProcessingWorkflow(db)
    wf2.storage_provider = storage
    wf2.ocr_provider = MockOCRProvider()
    wf2.extraction_provider = LocalExtractionProvider()
    await wf2.execute_job(job2.id)

    # Verify both records exist and supersession state in PostgreSQL
    res = await db.execute(
        select(DocumentValidationFlag)
        .where(DocumentValidationFlag.document_id == doc.id)
        .order_by(DocumentValidationFlag.created_at.asc())
    )
    all_flags = res.scalars().all()
    assert len(all_flags) == 2
    first_flag, second_flag = all_flags[0], all_flags[1]

    assert first_flag.superseded_at is not None
    assert second_flag.superseded_at is None
    assert first_flag.extraction_id != second_flag.extraction_id


@pytest.mark.asyncio
async def test_pg_search_returns_unlinked_document_by_filename(pg_test_env):
    """Exercise the real PostgreSQL LEFT JOIN with a persisted NULL patient_id."""
    db = pg_test_env["db"]
    org_id = pg_test_env["doc_a"].organization_id
    unlinked = Document(
        patient_id=None,
        organization_id=org_id,
        document_type="progress_note",
        source="UserUpload",
        file_name="unlinked-search-target.pdf",
        mime_type="application/pdf",
        status="completed",
        review_status="pending",
    )
    db.add(unlinked)
    await db.flush()

    items, total = await DocumentService(db).list_documents(
        search="unlinked-search-target",
        organization_id=org_id,
    )
    assert total == 1
    assert items[0]["id"] == str(unlinked.id)
    assert items[0]["patient_name"] is None


@pytest.mark.asyncio
async def test_pg_single_and_batch_approval_share_critical_flag_gate(pg_test_env):
    """The persisted CRITICAL rule blocks single and batch approval the same way."""
    db = pg_test_env["db"]
    document = pg_test_env["doc_a"]
    extraction = Extraction(document_id=document.id, status="completed")
    task = ReviewTask(document_id=document.id, status="pending", priority="normal")
    db.add_all([extraction, task])
    await db.flush()
    flag = DocumentValidationFlag(
        document_id=document.id,
        extraction_id=extraction.id,
        rule_code="CRITICAL",
        severity="critical",
        status="fail",
        message="Synthetic critical finding",
    )
    db.add(flag)
    await db.flush()

    service = ReviewService(db)
    with pytest.raises(ValueError, match="CONFLICT|CRITICAL"):
        await service.record_review_decision(
            task_id=task.id,
            decision="approved",
            reviewer_user_id=pg_test_env["reviewer"].id,
            acknowledged=False,
        )

    approved_count = await service.approve_clean_for_document(
        document.id,
        reviewer_user_id=pg_test_env["reviewer"].id,
        organization_id=document.organization_id,
    )
    await db.refresh(task)
    assert approved_count == 0
    assert task.status == "pending"

