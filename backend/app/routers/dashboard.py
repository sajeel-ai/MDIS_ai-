"""Dashboard API Router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.schemas.dashboard import DashboardMetricsResponse
from app.services.dashboard.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_roles(*tuple(UserRole)))])


@router.get("/dashboard", response_model=DashboardMetricsResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = DashboardService(db)
    return await service.get_dashboard_data()
