"""Broken Object Level Authorization (BOLA) and Tenant Verification."""

import uuid
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Document, Patient, User
from app.services.audit_service import record_audit_event


async def authorize_document_access(document_id: uuid.UUID, user: User, session: AsyncSession, request: Request | None = None) -> Document:
    res = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == user.organization_id,
        )
    )
    doc = res.scalars().first()
    if not doc:
        await record_audit_event(
            session, action="AUTHZ_DENIED", user_id=user.id,
            organization_id=user.organization_id, resource_type="document", resource_id=document_id,
            request=request,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return doc


async def authorize_patient_access(patient_id: uuid.UUID, user: User, session: AsyncSession, request: Request | None = None) -> Patient:
    res = await session.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.organization_id == user.organization_id,
        )
    )
    patient = res.scalars().first()
    if not patient:
        await record_audit_event(
            session, action="AUTHZ_DENIED", user_id=user.id,
            organization_id=user.organization_id, resource_type="patient", resource_id=patient_id,
            request=request,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient '{patient_id}' not found",
        )
    return patient
