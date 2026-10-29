"""Settings and Retention Policy API."""
import uuid
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.config import settings
from app.dependencies.auth import UserContext, UserRole, get_current_user
from app.dependencies.permissions import require_roles
from app.services.retention.retention_service import RetentionPurgeBlockedError, RetentionPurgeService
from app.services.audit_service import record_audit_event

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_roles(*tuple(UserRole)))])


@router.get("/retention-policy", response_model=Dict[str, Any])
async def get_retention_policy(
    current_user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the active data retention policy configuration."""
    service = RetentionPurgeService(db)
    return service.get_retention_policy()


@router.post(
    "/retention/purge",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
async def trigger_retention_purge(
    request: Request,
    dry_run: bool = Query(default=True),
    current_user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview by default; mutate only when dry_run=false and anonymous access is off."""
    if settings.allow_anonymous_access:
        raise HTTPException(status_code=403, detail="Retention purge is disabled when anonymous access is enabled")
    await record_audit_event(
        db,
        action="retention_purge_requested",
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="retention_policy",
        request=request,
        metadata={"dry_run": dry_run},
    )
    await db.commit()
    service = RetentionPurgeService(db)
    try:
        result = await service.run_retention_purge(dry_run=dry_run)
    except RetentionPurgeBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return result


@router.post(
    "/audit-events/{event_id}/legal-hold",
    response_model=Dict[str, Any],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
async def apply_audit_legal_hold(
    event_id: uuid.UUID,
    current_user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Place a permanent legal hold on an audit event."""
    if settings.allow_anonymous_access:
        raise HTTPException(status_code=403, detail="Legal holds are disabled when anonymous access is enabled")
    service = RetentionPurgeService(db)
    applied = await service.place_legal_hold(
        event_id,
        user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    if not applied:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return {"status": "legal_hold_applied", "event_id": str(event_id), "legal_hold": True}

