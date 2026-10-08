"""AI Operations Telemetry API Router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.schemas.aiops import (
    AIOpsMetricsResponse,
    AIOpsJobsResponse,
    AIOpsHealthResponse,
)
from app.services.aiops.aiops_service import AIOperationsService

router = APIRouter(prefix="/aiops", tags=["aiops"], dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))])


@router.get("/metrics", response_model=AIOpsMetricsResponse)
async def get_aiops_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = AIOperationsService(db)
    return await service.get_aiops_metrics()


@router.get("/jobs", response_model=AIOpsJobsResponse)
async def get_aiops_jobs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = AIOperationsService(db)
    return {"jobs": await service.get_recent_jobs(limit=limit)}


@router.get("/health", response_model=AIOpsHealthResponse)
async def get_aiops_health(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = AIOperationsService(db)
    metrics = await service.get_aiops_metrics()
    return {
        "status": "healthy" if metrics["failed_jobs"] == 0 else "degraded",
        "active_jobs": metrics["running_jobs"],
        "avg_confidence": metrics["avg_confidence"],
        "pipeline": "operational",
    }
