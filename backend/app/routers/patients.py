"""Patients API Router."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.models import Patient
from app.schemas.common import PaginatedResponse
from app.schemas.patient import PatientResponse, PatientTimelineResponse
from app.services.patients.patient_service import PatientService
from app.security.authorization import authorize_patient_access
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/patients", tags=["patients"], dependencies=[Depends(require_roles(*tuple(UserRole)))])


@router.get("", response_model=PaginatedResponse[PatientResponse])
async def list_patients(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    """List patients with optional MRN/name search."""
    await record_audit_event(db, action="list_patients", user_id=current_user.id, organization_id=current_user.organization_id)
    base_query = select(Patient)
    if current_user.organization_id is not None:
        base_query = base_query.where(Patient.organization_id == current_user.organization_id)

    if search:
        term = f"%{search}%"
        from sqlalchemy import or_
        base_query = base_query.where(
            or_(
                Patient.mrn.ilike(term),
                Patient.first_name.ilike(term),
                Patient.last_name.ilike(term),
                Patient.external_patient_id.ilike(term),
            )
        )

    count_res = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_res.scalar() or 0

    offset = (page - 1) * page_size
    query = base_query.order_by(Patient.created_at.desc()).offset(offset).limit(page_size)
    res = await db.execute(query)
    patients = res.scalars().all()

    items = [
        PatientResponse(
            id=str(p.id),
            external_patient_id=p.external_patient_id,
            mrn=p.mrn,
            first_name=p.first_name,
            last_name=p.last_name,
            gender=p.gender,
            dob=p.dob.strftime("%Y-%m-%d") if p.dob else None,
        )
        for p in patients
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


@router.get("/{patient_id}/timeline", response_model=PatientTimelineResponse)
async def get_patient_timeline(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
    request: Request = None,
):
    await authorize_patient_access(patient_id, current_user, db, request)
    service = PatientService(db)
    timeline = await service.get_patient_timeline(patient_id)
    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found",
        )
    await record_audit_event(db, action="view_patient_timeline", user_id=current_user.id, organization_id=current_user.organization_id, resource_type="patient", resource_id=patient_id)
    return timeline
