"""Tenant isolation, upload validation, and audit metadata regression tests."""

import io
import uuid
import pymupdf as fitz
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.db import AsyncSessionLocal, engine, get_db
from app.main import app
from app.models import (
    AuditEvent, ClinicalEntity, Document, DocumentVersion, EvidenceSpan, Extraction,
    Organization, Patient, ProcessingJob, ReviewTask, User, UserRole,
)
from app.security.auth import create_access_token
from app.services.audit_service import record_audit_event


@pytest_asyncio.fixture
async def tenant_data():
    await engine.dispose(close=False)
    async with AsyncSessionLocal() as db:
        org_a = Organization(name="Synthetic tenant A")
        org_b = Organization(name="Synthetic tenant B")
        db.add_all([org_a, org_b])
        await db.flush()
        user = User(
            email=f"tenant-{uuid.uuid4()}@example.test",
            role=UserRole.CLINICIAN,
            organization_id=org_a.id,
            is_active=True,
        )
        operator = User(
            email=f"operator-{uuid.uuid4()}@example.test",
            role=UserRole.OPERATOR,
            organization_id=org_a.id,
            is_active=True,
            mfa_enabled=True,
        )
        admin = User(
            email=f"admin-{uuid.uuid4()}@example.test",
            role=UserRole.ADMIN,
            organization_id=org_a.id,
            is_active=True,
            mfa_enabled=True,
        )
        user_b = User(
            email=f"tenant-b-{uuid.uuid4()}@example.test",
            role=UserRole.CLINICIAN,
            organization_id=org_b.id,
            is_active=True,
        )
        patient_a = Patient(
            external_patient_id=f"SYN-{uuid.uuid4().hex[:8]}",
            organization_id=org_a.id,
        )
        patient_b = Patient(
            external_patient_id=f"SYN-{uuid.uuid4().hex[:8]}",
            organization_id=org_b.id,
        )
        db.add_all([user, operator, admin, user_b, patient_a, patient_b])
        await db.flush()
        document_a = Document(
            patient_id=patient_a.id,
            organization_id=org_a.id,
            document_type="synthetic_note",
            source="synthetic",
            file_name="synthetic-a.txt",
            mime_type="text/plain",
            size_bytes=0,
            status="uploaded",
            review_status="not_required",
        )
        document_b = Document(
            patient_id=patient_b.id,
            organization_id=org_b.id,
            document_type="synthetic_note",
            source="synthetic",
            file_name="synthetic-b.txt",
            mime_type="text/plain",
            size_bytes=0,
            status="uploaded",
            review_status="not_required",
        )
        db.add_all([document_a, document_b])
        await db.flush()
        document_version_b = DocumentVersion(
            document_id=document_b.id,
            version_number=1,
            raw_text="Synthetic evidence text",
            text_hash="a" * 64,
            page_count=1,
        )
        extraction_b = Extraction(document_id=document_b.id, status="completed")
        db.add_all([document_version_b, extraction_b])
        await db.flush()
        entity_b = ClinicalEntity(
            extraction_id=extraction_b.id,
            entity_type="diagnosis",
            raw_text="synthetic diagnosis",
            normalized_value="synthetic diagnosis",
            confidence=0.5,
        )
        db.add(entity_b)
        await db.flush()
        evidence_b = EvidenceSpan(
            entity_id=entity_b.id,
            document_version_id=document_version_b.id,
            start_offset=0,
            end_offset=23,
            text="Synthetic evidence text",
        )
        review_task_b = ReviewTask(document_id=document_b.id, entity_id=entity_b.id, reason="synthetic test task")
        audit_b = AuditEvent(organization_id=org_b.id, action="synthetic_test_event", resource_type="document", resource_id=document_b.id)
        db.add_all([evidence_b, review_task_b, audit_b])
        job_b = ProcessingJob(document_id=document_b.id, status="queued", pipeline_version="test")
        db.add(job_b)
        await db.commit()
        data = {
            "db": db,
            "user": user,
            "operator": operator,
            "admin": admin,
            "user_b": user_b,
            "org_a": org_a,
            "org_b": org_b,
            "patient_a": patient_a,
            "patient_b": patient_b,
            "document_a": document_a,
            "document_b": document_b,
            "org_a_id": org_a.id,
            "org_b_id": org_b.id,
            "user_id": user.id,
            "patient_a_id": patient_a.id,
            "patient_b_id": patient_b.id,
            "document_a_id": document_a.id,
            "document_b_id": document_b.id,
            "job_b_id": job_b.id,
            "review_task_b_id": review_task_b.id,
        }
        try:
            yield data
        finally:
            await db.rollback()
            db.info.clear()
            entity_ids = select(ClinicalEntity.id).join(Extraction).where(Extraction.document_id.in_([data["document_a_id"], data["document_b_id"]]))
            await db.execute(delete(EvidenceSpan).where(EvidenceSpan.entity_id.in_(entity_ids)))
            await db.execute(delete(Document).where(Document.id.in_([data["document_a_id"], data["document_b_id"]])))
            await db.execute(delete(Patient).where(Patient.id.in_([data["patient_a_id"], data["patient_b_id"]])))
            await db.commit()
            app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def tenant_client(tenant_data):
    db = tenant_data["db"]

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    token = create_access_token({"sub": str(tenant_data["user"].id)})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def tenant_operator_client(tenant_data):
    db = tenant_data["db"]

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    token = create_access_token({"sub": str(tenant_data["operator"].id)})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def tenant_admin_client(tenant_data):
    db = tenant_data["db"]

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    token = create_access_token({"sub": str(tenant_data["admin"].id)})
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_patient_and_document_lists_only_return_callers_organization(tenant_data, tenant_client):
    patients = await tenant_client.get("/api/v1/patients")
    documents = await tenant_client.get("/api/v1/documents")
    assert patients.status_code == 200
    assert {item["id"] for item in patients.json()["items"]} == {str(tenant_data["patient_a"].id)}
    assert documents.status_code == 200
    assert {item["id"] for item in documents.json()["items"]} == {str(tenant_data["document_a"].id)}


@pytest.mark.asyncio
async def test_cross_organization_document_and_patient_are_not_found(tenant_data, tenant_client):
    doc_response = await tenant_client.get(f"/api/v1/documents/{tenant_data['document_b'].id}")
    patient_response = await tenant_client.get(f"/api/v1/patients/{tenant_data['patient_b'].id}/timeline")
    assert doc_response.status_code == 404
    assert patient_response.status_code == 404
    job_response = await tenant_client.get(f"/api/v1/processing/{tenant_data['job_b_id']}")
    job_steps_response = await tenant_client.get(f"/api/v1/processing/{tenant_data['job_b_id']}/steps")
    assert job_response.status_code == 404
    assert job_steps_response.status_code == 404


@pytest.mark.asyncio
async def test_cross_organization_entities_evidence_and_review_are_not_found(tenant_data, tenant_client):
    document_id = tenant_data["document_b"].id
    entities = await tenant_client.get(f"/api/v1/documents/{document_id}/entities")
    evidence = await tenant_client.get(f"/api/v1/documents/{document_id}/evidence")
    review = await tenant_client.get(f"/api/v1/review/{tenant_data['review_task_b_id']}")
    fhir = await tenant_client.get(f"/api/v1/documents/{document_id}/fhir")
    csv_export = await tenant_client.get(f"/api/v1/documents/{document_id}/export/csv")
    assert entities.status_code == 404
    assert evidence.status_code == 404
    assert review.status_code == 404
    assert fhir.status_code == 404
    assert csv_export.status_code == 404


@pytest.mark.asyncio
async def test_audit_list_is_organization_scoped_for_operator(tenant_data, tenant_operator_client):
    response = await tenant_operator_client.get("/api/v1/audit/events")
    assert response.status_code == 200, response.text
    assert all(item["resource_id"] != str(tenant_data["document_b"].id) for item in response.json()["items"])


@pytest.mark.asyncio
async def test_admin_user_management_hides_cross_organization_accounts(tenant_data, tenant_admin_client):
    users = await tenant_admin_client.get("/api/v1/admin/users")
    sessions = await tenant_admin_client.get(f"/api/v1/admin/users/{tenant_data['user_b'].id}/sessions")
    role_change = await tenant_admin_client.patch(
        f"/api/v1/admin/users/{tenant_data['user_b'].id}/role",
        json={"role": "viewer"},
    )
    assert users.status_code == 200
    assert all(item["id"] != str(tenant_data["user_b"].id) for item in users.json())
    assert sessions.status_code == 404
    assert role_change.status_code == 404


@pytest.mark.asyncio
async def test_missing_token_gets_401_and_wrong_role_gets_403(tenant_data, tenant_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing_token = await client.get("/api/v1/patients")
    assert missing_token.status_code == 401

    denied = await tenant_client.get("/api/v1/aiops/health")
    assert denied.status_code == 403, denied.text


def make_pdf(page_count: int) -> bytes:
    pdf = fitz.open()
    for _ in range(page_count):
        pdf.new_page()
    data = pdf.tobytes()
    pdf.close()
    return data


async def upload(client: AsyncClient, patient_id: uuid.UUID, filename: str, data: bytes, content_type: str):
    return await client.post(
        "/api/v1/documents/upload",
        data={"patient_id": str(patient_id), "document_type": "synthetic_note"},
        files={"file": (filename, io.BytesIO(data), content_type)},
    )


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(tenant_data, tenant_client):
    response = await upload(tenant_client, tenant_data["patient_a"].id, "note.csv", b"synthetic", "text/csv")
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(tenant_data, tenant_client):
    response = await upload(tenant_client, tenant_data["patient_a"].id, "note.txt", b"", "text/plain")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_ignores_client_mime_and_checks_magic_bytes(tenant_data, tenant_client):
    response = await upload(tenant_client, tenant_data["patient_a"].id, "note.pdf", b"not a pdf", "application/pdf")
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_files_over_configured_limit(monkeypatch, tenant_data, tenant_client):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 4)
    response = await upload(tenant_client, tenant_data["patient_a"].id, "note.txt", b"too large", "text/plain")
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_documents_over_configured_page_limit(monkeypatch, tenant_data, tenant_client):
    monkeypatch.setattr(settings, "max_document_pages", 2)
    response = await upload(tenant_client, tenant_data["patient_a"].id, "note.pdf", make_pdf(3), "application/pdf")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_successful_upload_stores_content_hash_and_audit_ids_only(tenant_data, tenant_client):
    content = make_pdf(1)
    response = await upload(
        tenant_client,
        tenant_data["patient_a"].id,
        "../synthetic note.pdf",
        content,
        "text/plain",
    )
    assert response.status_code == 201
    document_id = uuid.UUID(response.json()["id"])
    stored_document = await tenant_data["db"].get(Document, document_id)
    assert stored_document is not None
    assert stored_document.file_name == "synthetic_note.pdf"
    assert stored_document.storage_key == f"documents/{__import__('hashlib').sha256(content).hexdigest()}"
    audit = await tenant_data["db"].scalar(
        select(AuditEvent).where(
            AuditEvent.action == "upload_document",
            AuditEvent.resource_id == document_id,
        )
    )
    assert audit is not None
    assert audit.metadata_ == {
        "action": "upload_document",
        "resource_id": str(document_id),
        "organization_id": str(tenant_data["org_a"].id),
    }


@pytest.mark.asyncio
async def test_audit_row_metadata_contains_only_action_and_identifiers(tenant_data):
    db = tenant_data["db"]
    event = await record_audit_event(
        db,
        action="view_document",
        user_id=tenant_data["user"].id,
        organization_id=tenant_data["org_a"].id,
        resource_type="document",
        resource_id=tenant_data["document_a"].id,
    )
    await db.commit()
    stored = await db.scalar(select(AuditEvent).where(AuditEvent.id == event.id))
    assert stored is not None
    assert stored.metadata_ == {
        "action": "view_document",
        "resource_id": str(tenant_data["document_a"].id),
        "organization_id": str(tenant_data["org_a"].id),
    }
    assert all(isinstance(value, str) for value in stored.metadata_.values())


@pytest.mark.asyncio
async def test_audit_rows_reject_updates(tenant_data):
    db = tenant_data["db"]
    event = await record_audit_event(
        db,
        action="view_document",
        user_id=tenant_data["user"].id,
        organization_id=tenant_data["org_a"].id,
        resource_type="document",
        resource_id=tenant_data["document_a"].id,
    )
    await db.commit()
    with pytest.raises(DBAPIError):
        await db.execute(
            update(AuditEvent)
            .where(AuditEvent.id == event.id)
            .values(action="modified")
        )
    await db.rollback()
