"""Organization-scoped command-palette search."""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.models import ClinicalEntity, Document, Extraction, Patient
from app.services.audit_service import record_audit_event
from app.services.auth_rate_limit import enforce_auth_rate_limit
from app.workflows.states import derive_lifecycle_status
from app.db import get_db

router = APIRouter(
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)


class SearchRequest(BaseModel):
    q: str = Field(min_length=3, max_length=128)


def _item(item_id: uuid.UUID, label: str, status: str, item_type: str) -> dict:
    return {"id": str(item_id), "display_label": label[:256], "status": status, "type": item_type}


@router.post("")
async def global_search(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    query = payload.q.strip()
    if len(query) < 3:
        return {"documents": [], "patients": [], "findings": []}

    await enforce_auth_rate_limit(request, db, "global_search")
    term = f"%{query}%"
    organization_id = current_user.organization_id

    document_rows = (
        await db.execute(
            select(Document)
            .join(Patient, Patient.id == Document.patient_id)
            .where(
                Document.organization_id == organization_id,
                Patient.organization_id == organization_id,
                or_(
                    Document.file_name.ilike(term),
                    Document.document_type.ilike(term),
                    Patient.first_name.ilike(term),
                    Patient.last_name.ilike(term),
                    Patient.mrn.ilike(term),
                ),
            )
            .order_by(Document.updated_at.desc())
            .limit(10)
        )
    ).scalars().all()

    patient_rows = (
        await db.execute(
            select(Patient)
            .where(
                Patient.organization_id == organization_id,
                or_(
                    Patient.first_name.ilike(term),
                    Patient.last_name.ilike(term),
                    Patient.mrn.ilike(term),
                    Patient.external_patient_id.ilike(term),
                ),
            )
            .order_by(Patient.updated_at.desc())
            .limit(10)
        )
    ).scalars().all()

    finding_rows = (
        await db.execute(
            select(ClinicalEntity, Document)
            .join(Extraction, Extraction.id == ClinicalEntity.extraction_id)
            .join(Document, Document.id == Extraction.document_id)
            .where(
                Document.organization_id == organization_id,
                or_(
                    ClinicalEntity.raw_text.ilike(term),
                    ClinicalEntity.normalized_value.ilike(term),
                    ClinicalEntity.entity_type.ilike(term),
                ),
            )
            .order_by(ClinicalEntity.created_at.desc())
            .limit(10)
        )
    ).all()

    await record_audit_event(
        db,
        action="global_search",
        user_id=current_user.id,
        organization_id=organization_id,
        request=request,
        metadata={"query_length": len(query)},
    )

    documents = [
        _item(
            doc.id,
            doc.file_name or doc.document_type.replace("_", " ").title(),
            derive_lifecycle_status(doc.status, doc.review_status),
            "document",
        )
        for doc in document_rows
    ]
    patients = [
        _item(
            patient.id,
            " ".join(part for part in (patient.first_name, patient.last_name) if part)
            or patient.mrn
            or patient.external_patient_id
            or "Patient",
            "extracted",
            "patient",
        )
        for patient in patient_rows
    ]
    findings = [
        _item(
            entity.id,
            entity.normalized_value or entity.raw_text,
            derive_lifecycle_status(document.status, document.review_status),
            "finding",
        )
        for entity, document in finding_rows
    ]
    return {"documents": documents, "patients": patients, "findings": findings}
