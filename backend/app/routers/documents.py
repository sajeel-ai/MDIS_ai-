"""Documents API Router."""

import hashlib
from io import BytesIO
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Response, BackgroundTasks, UploadFile, File, Form, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import pymupdf as fitz
from PIL import Image, ImageOps
from pydantic import BaseModel

from app.db import get_db, AsyncSessionLocal
from app.dependencies import UserContext, get_current_user, audit_read_access
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
from app.models import DocumentValidationFlag
from sqlalchemy import select
from app.security.authorization import authorize_document_access, authorize_patient_access
from app.services.audit_service import record_audit_event

router = APIRouter(
    prefix="/documents", tags=["documents"],
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)


class PatientLinkRequest(BaseModel):
    patient_id: uuid.UUID


def render_page_png(content: bytes, mime_type: str, page_number: int, max_edge: int = 2048) -> bytes:
    """Render a PDF/image page in memory with a bounded longest edge."""
    source = BytesIO(content)
    if mime_type == "application/pdf":
        with fitz.open(stream=content, filetype="pdf") as pdf:
            if page_number > pdf.page_count:
                raise ValueError("Document page not found")
            page = pdf.load_page(page_number - 1)
            scale = min(2.0, max_edge / max(page.rect.width, page.rect.height))
            return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
    if mime_type.startswith("image/"):
        with Image.open(source) as opened:
            if page_number > getattr(opened, "n_frames", 1):
                raise ValueError("Document page not found")
            opened.seek(page_number - 1)
            image = ImageOps.exif_transpose(opened.copy())
            image.thumbnail((max_edge, max_edge))
            output = BytesIO()
            image.convert("RGB").save(output, format="PNG")
            return output.getvalue()
    raise NotImplementedError("Page rendering is unavailable for this document type")


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
    try:
        with tempfile.NamedTemporaryFile(prefix="upload-", suffix=extension, dir=settings.storage_local_path, delete=False) as staged:
            temp_path = staged.name
            while chunk := await file.read(64 * 1024):
                size_bytes += len(chunk)
                if size_bytes > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds the configured upload size limit.")
                digest.update(chunk)
                staged.write(chunk)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        # Item 4: charset_normalizer-based encoding detection for .txt files.
        # Accepts UTF-8, Windows-1252, Latin-1, and other common encodings.
        if extension == ".txt":
            with open(temp_path, "rb") as _f:
                _raw = _f.read()
            if b"\x00" in _raw:
                raise HTTPException(status_code=415, detail="TXT upload must not contain null bytes.")
            from charset_normalizer import from_bytes as _detect
            _best = _detect(_raw).best()
            if _best is None:
                raise HTTPException(
                    status_code=415,
                    detail="Unable to detect text encoding; upload a UTF-8 or common 8-bit encoded text file.",
                )

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
            try:
                os.remove(temp_path)
            except OSError:
                pass


@router.get("", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    doc_status: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    unlinked_patient: bool = Query(False),
    sort: str = Query("updated_desc", pattern="^(updated_desc|name_asc|status_asc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(db, action="list_documents", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="document_collection", request=request)
    await db.commit()
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
    for item in items:
        await record_audit_event(
            db,
            action="view_document_in_list",
            user_id=current_user.id,
            organization_id=current_user.organization_id,
            resource_type="document",
            resource_id=uuid.UUID(str(item["id"])),
            request=request,
        )
    if items:
        await db.commit()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


@router.post("/{document_id}/patient", dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.ADMIN))])
async def link_document_patient(
    document_id: uuid.UUID,
    payload: PatientLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    document = await authorize_document_access(document_id, current_user, db, request)
    patient = await authorize_patient_access(payload.patient_id, current_user, db, request)
    if patient.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Deleted patients cannot be linked to documents")
    document.patient_id = patient.id
    await record_audit_event(
        db, action="link_document_patient", user_id=current_user.id,
        organization_id=current_user.organization_id, resource_type="document",
        resource_id=document.id, request=request,
    )
    await db.commit()
    return {"document_id": str(document.id), "patient_id": str(patient.id)}


@router.get("/{document_id}/processing", dependencies=[Depends(audit_read_access("read_processing_status"))])
async def get_document_processing_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    document = await authorize_document_access(document_id, current_user, db, request)
    from app.models import ProcessingJob, ProcessingStep

    job = await db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        return {"status": "uploaded", "stages": [], "failure_reason": None, "retryable": None}
    steps = (await db.scalars(
        select(ProcessingStep).where(ProcessingStep.processing_job_id == job.id)
        .order_by(ProcessingStep.created_at)
    )).all()
    return {
        "status": "failed" if job.status == "failed" else "ready_for_review" if job.status == "completed" else job.status,
        "stages": [{"name": step.step_name, "status": step.status} for step in steps],
        "failure_reason": job.error_message if job.status == "failed" else None,
        "retryable": True if job.status == "failed" and job.error_code and job.error_code.startswith("PROCESSING_") else False if job.status == "failed" else None,
    }


@router.get("/{document_id}", response_model=DocumentDetailResponse, dependencies=[Depends(audit_read_access("view_document"))])
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
    return doc_data


@router.get("/{document_id}/entities", response_model=List[ClinicalEntityResponse], dependencies=[Depends(audit_read_access("view_entities"))])
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
    return entities


@router.get(
    "/{document_id}/validation-flags",
    dependencies=[Depends(audit_read_access("view_validation_flags"))],
)
async def get_document_validation_flags(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    """Read active and superseded validation findings with PHI access auditing."""
    await authorize_document_access(document_id, current_user, db, request)
    result = await db.execute(
        select(DocumentValidationFlag)
        .where(DocumentValidationFlag.document_id == document_id)
        .order_by(DocumentValidationFlag.created_at.asc())
    )
    flags = result.scalars().all()
    return [
        {
            "id": str(flag.id),
            "document_id": str(flag.document_id),
            "extraction_id": str(flag.extraction_id),
            "rule_code": flag.rule_code,
            "severity": flag.severity,
            "status": flag.status,
            "message": flag.message,
            "details": flag.details,
            "superseded_at": flag.superseded_at.isoformat() if flag.superseded_at else None,
            "created_at": flag.created_at.isoformat() if flag.created_at else None,
        }
        for flag in flags
    ]


@router.get("/{document_id}/evidence", response_model=List[EvidenceSpanResponse], dependencies=[Depends(audit_read_access("view_evidence"))])
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
    return evidence

@router.get("/{document_id}/file", dependencies=[Depends(audit_read_access("read_file"))])
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    document = await authorize_document_access(document_id, current_user, db, request)
    if not document.storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")
    from app.providers.storage import get_storage_provider
    provider = get_storage_provider()
    try:
        content = await provider.read_file(document.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found in storage")
    return Response(content=content, media_type=document.mime_type or "application/octet-stream", headers={"Cache-Control": "no-store"})


@router.get("/{document_id}/pages/{page_number}/image", dependencies=[Depends(audit_read_access("read_page_image"))])
async def get_document_page_image(
    document_id: uuid.UUID,
    page_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    """Render one authenticated page in memory; do not create plaintext temp files."""
    if page_number < 1:
        raise HTTPException(status_code=404, detail="Document page not found")
    document = await authorize_document_access(document_id, current_user, db, request)
    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document file not found")
    from app.providers.storage import get_storage_provider

    try:
        content = await get_storage_provider().read_file(document.storage_key)
        if not document.mime_type:
            raise HTTPException(status_code=415, detail="Page rendering is unavailable for this document type")
        rendered = render_page_png(content, document.mime_type, page_number)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document file not found in storage") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    return Response(content=rendered, media_type="image/png", headers={"Cache-Control": "no-store"})



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
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
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


@router.get("/{document_id}/fhir", dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.REVIEWER, UserRole.ADMIN)), Depends(audit_read_access("export_fhir"))])
async def get_document_fhir(
    document_id: uuid.UUID,
    include_unreviewed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_document_access(document_id, current_user, db, request)
    service = FHIRProjectionService(db)
    try:
        bundle = await service.generate_document_fhir_bundle(document_id, include_unreviewed=include_unreviewed)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)

    if not bundle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return bundle


@router.get("/{document_id}/export/{export_format}", dependencies=[Depends(require_roles(UserRole.CLINICIAN, UserRole.REVIEWER, UserRole.ADMIN)), Depends(audit_read_access("export_document"))])
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
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=msg,
            )
        if "linked patient" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
