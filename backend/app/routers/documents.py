"""Documents API Router."""

import codecs
import hashlib
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Response, BackgroundTasks, UploadFile, File, Form, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import pymupdf as fitz
from PIL import Image

from app.db import get_db, AsyncSessionLocal
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.schemas.common import PaginatedResponse
from app.schemas.document import (
    DocumentResponse,
    DocumentDetailResponse,
    DocumentProcessResponse,
)
from app.schemas.extraction import ClinicalEntityResponse, EvidenceSpanResponse
from app.services.documents.document_service import DocumentService
from app.services.processing.job_service import JobService, ProcessingConflictError
from app.services.fhir.fhir_service import FHIRProjectionService
from app.services.export.exporter import ExporterService
from app.providers.extraction import ExtractionProviderConfigurationError
from app.config import settings
from app.security.authorization import authorize_document_access, authorize_patient_access
from app.services.audit_service import record_audit_event

router = APIRouter(
    prefix="/documents", tags=["documents"],
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)


async def run_async_processing_task(job_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        from app.models import Document, ProcessingJob

        session.info["scope_required"] = True
        session.info["allow_unscoped_job_lookup"] = True
        try:
            result = await session.execute(
                select(ProcessingJob.id, Document.organization_id)
                .join(Document, ProcessingJob.document_id == Document.id)
                .where(ProcessingJob.id == job_id)
            )
        finally:
            session.info.pop("allow_unscoped_job_lookup", None)
        job_scope = result.first()
        if job_scope is None or job_scope.organization_id is None:
            return
        session.info["organization_id"] = job_scope.organization_id
        job_service = JobService(session)
        await job_service.run_job_workflow(job_id)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.ADMIN))])
async def upload_document(
    patient_id: uuid.UUID = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    service = DocumentService(db)
    raw_name = file.filename or "upload"
    extension = Path(raw_name.replace("\\", "/")).suffix.lower()
    if extension not in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".txt"}:
        raise HTTPException(status_code=415, detail="Unsupported file type. Upload PDF, PNG, JPG, JPEG, TIFF, or TXT.")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw_name.replace("\\", "/")).name)
    safe_name = safe_name.lstrip(".")[:256] or f"upload{extension}"
    os.makedirs(settings.storage_local_path, exist_ok=True)
    temp_path = None
    size_bytes = 0
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")("strict") if extension == ".txt" else None
    try:
        with tempfile.NamedTemporaryFile(prefix="upload-", suffix=extension, dir=settings.storage_local_path, delete=False) as staged:
            temp_path = staged.name
            while chunk := await file.read(64 * 1024):
                size_bytes += len(chunk)
                if size_bytes > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds the configured upload size limit.")
                if decoder is not None:
                    if b"\x00" in chunk:
                        raise HTTPException(status_code=415, detail="TXT upload must be valid UTF-8 text.")
                    try:
                        decoder.decode(chunk)
                    except UnicodeDecodeError as exc:
                        raise HTTPException(status_code=415, detail="TXT upload must be valid UTF-8 text.") from exc
                digest.update(chunk)
                staged.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        if decoder is not None:
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=415, detail="TXT upload must be valid UTF-8 text.") from exc

        with open(temp_path, "rb") as staged:
            header = staged.read(16)
        signatures = {
            ".pdf": header.startswith(b"%PDF-"),
            ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": header.startswith(b"\xff\xd8\xff"),
            ".jpeg": header.startswith(b"\xff\xd8\xff"),
            ".tiff": header.startswith((b"II*\x00", b"MM\x00*")),
            ".txt": True,
        }
        if not signatures[extension]:
            raise HTTPException(status_code=415, detail="File contents do not match the file extension.")

        mime_types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".tiff": "image/tiff", ".txt": "text/plain"}
        try:
            if extension == ".pdf":
                with fitz.open(temp_path) as pdf:
                    page_count = pdf.page_count
            elif extension == ".tiff":
                with Image.open(temp_path) as image:
                    page_count = getattr(image, "n_frames", 1)
            else:
                page_count = 1
        except Exception:
            raise HTTPException(status_code=415, detail="The uploaded file is invalid or unreadable.") from None
        if page_count > settings.max_document_pages:
            raise HTTPException(status_code=422, detail="Document exceeds the configured page limit.")

        doc_resp = await service.upload_document(
            patient_id=patient_id,
            document_type=document_type,
            file_bytes=b"",
            file_name=safe_name,
            mime_type=mime_types[extension],
            file_path=temp_path,
            content_hash=digest.hexdigest(),
        )
        await record_audit_event(db, action="upload_document", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=uuid.UUID(doc_resp["id"]))
        return doc_resp
    except ValueError as exc:
        await record_audit_event(
            db,
            action="AUTHZ_DENIED",
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            resource_type="patient",
            resource_id=patient_id,
            request=request,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        ) from exc
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.get("", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    doc_status: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    unlinked_patient: bool = Query(False),
    sort: str = Query("updated_desc", pattern="^(updated_desc|name_asc|status_asc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(db, action="list_documents", user_id=current_user.id, organization_id=current_user.organization_id)
    service = DocumentService(db)
    items, total = await service.list_documents(
        page=page,
        page_size=page_size,
        status=doc_status,
        search=search,
        unlinked_patient=unlinked_patient,
        sort=sort,
        organization_id=current_user.organization_id,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    service = DocumentService(db)
    doc_data = await service.get_document_details(document_id)
    if not doc_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    await record_audit_event(db, action="view_document", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    return doc_data


@router.get("/{document_id}/entities", response_model=List[ClinicalEntityResponse])
async def get_document_entities(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    service = DocumentService(db)
    entities = await service.get_document_entities(document_id)
    if entities is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    await record_audit_event(db, action="view_entities", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    return entities


@router.get("/{document_id}/evidence", response_model=List[EvidenceSpanResponse])
async def get_document_evidence(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    service = DocumentService(db)
    evidence = await service.get_document_evidence(document_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    await record_audit_event(db, action="view_evidence", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    return evidence


@router.post("/{document_id}/process", response_model=DocumentProcessResponse, dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.ADMIN))])
async def process_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    job_service = JobService(db)
    try:
        request = await job_service.create_and_enqueue_job(document_id)
    except ExtractionProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except ProcessingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    job = request.job
    await record_audit_event(db, action="process_document", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    if request.created:
        background_tasks.add_task(run_async_processing_task, job.id)
    return {
        "job_id": str(job.id),
        "document_id": str(document_id),
        "status": job.status,
        "message": (
            "Async document processing initiated"
            if request.created
            else f"Existing processing job returned ({job.status})"
        ),
    }


@router.post("/{document_id}/process/retry", response_model=DocumentProcessResponse, dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.ADMIN))])
async def retry_document_processing(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    job_service = JobService(db)
    try:
        request = await job_service.retry_failed_job(document_id)
    except ExtractionProviderConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except ProcessingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    job = request.job
    await record_audit_event(db, action="retry_document", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    if request.created:
        background_tasks.add_task(run_async_processing_task, job.id)
    return {
        "job_id": str(job.id),
        "document_id": str(document_id),
        "status": job.status,
        "message": (
            "Explicit document processing retry initiated"
            if request.created
            else f"Existing processing job returned ({job.status})"
        ),
    }


@router.post("/{document_id}/reprocess", response_model=DocumentProcessResponse, dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.ADMIN))])
async def reprocess_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    """Replace prior extraction output with a fresh OCR/AI run."""
    await authorize_document_access(document_id, current_user, db, request)
    job_service = JobService(db)
    try:
        process_request = await job_service.reprocess_document(document_id)
    except ExtractionProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ProcessingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    job = process_request.job
    await record_audit_event(db, action="reprocess_document", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    if process_request.created:
        background_tasks.add_task(run_async_processing_task, job.id)
    return {
        "job_id": str(job.id),
        "document_id": str(document_id),
        "status": job.status,
        "message": "Fresh document extraction initiated" if process_request.created else f"Existing processing job returned ({job.status})",
    }


@router.get("/{document_id}/fhir", dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.REVIEWER, UserRole.ADMIN))])
async def get_document_fhir(
    document_id: uuid.UUID,
    include_unreviewed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    service = FHIRProjectionService(db)
    bundle = await service.generate_document_fhir_bundle(document_id, include_unreviewed=include_unreviewed)
    if not bundle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    await record_audit_event(db, action="export_fhir", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
    return bundle


@router.get("/{document_id}/export/{export_format}", dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.REVIEWER, UserRole.ADMIN))])
async def export_document(
    document_id: uuid.UUID,
    export_format: str,
    include_unreviewed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    exporter = ExporterService(db)
    try:
        content, media_type, filename = await exporter.export_document(document_id, export_format, include_unreviewed=include_unreviewed)
        export_action = "export_csv" if export_format.lower() == "csv" else "export_fhir" if export_format.lower() == "fhir" else "export_json"
        await record_audit_event(db, action=export_action, user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document", resource_id=document_id)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
