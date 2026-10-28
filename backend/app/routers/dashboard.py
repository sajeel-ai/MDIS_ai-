"""Dashboard API Router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.dependencies.audit_read import audit_read_access
from app.schemas.dashboard import DashboardMetricsResponse
from app.services.dashboard.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"], dependencies=[
    Depends(require_roles(*tuple(UserRole))),
    Depends(audit_read_access("read_dashboard", resource_type="dashboard")),
])


@router.get("/dashboard", response_model=DashboardMetricsResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    if current_user.organization_id is None:
        raise HTTPException(status_code=403, detail="An organization is required to view dashboard data.")
    service = DashboardService(db, organization_id=current_user.organization_id)
    return await service.get_dashboard_data()
