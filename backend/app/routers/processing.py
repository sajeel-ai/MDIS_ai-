"""Processing Job Status API Router."""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.schemas.processing import ProcessingJobResponse, ProcessingJobStepsResponse
from app.services.processing.job_service import JobService
from app.dependencies.audit_read import audit_read_access

router = APIRouter(prefix="/processing", tags=["processing"], dependencies=[Depends(require_roles(*tuple(UserRole)))])


@router.get("/{job_id}", response_model=ProcessingJobResponse, dependencies=[Depends(audit_read_access("read_processing_job", resource_type="processing_job"))])
async def get_processing_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = JobService(db)
    status_data = await service.get_job_status(job_id)
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job '{job_id}' not found",
        )
    return status_data


@router.get("/{job_id}/steps", response_model=ProcessingJobStepsResponse, dependencies=[Depends(audit_read_access("read_processing_job_steps", resource_type="processing_job"))])
async def get_processing_job_steps(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = JobService(db)
    status_data = await service.get_job_status(job_id)
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing job '{job_id}' not found",
        )
    return {"job_id": str(job_id), "steps": status_data["steps"]}
