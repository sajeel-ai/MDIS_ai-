"""Audit log API."""

import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.models import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))])


@router.get("/events")
async def list_audit_events(
    limit: int = Query(50, ge=1, le=200),
    resource_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    query = select(AuditEvent).where(AuditEvent.organization_id == current_user.organization_id)
    if resource_id is not None:
        query = query.where(AuditEvent.resource_id == resource_id)
    result = await db.execute(
        query
        .options(selectinload(AuditEvent.user))
        .order_by(desc(AuditEvent.created_at))
        .limit(limit)
    )
    return {
        "items": [
            {
                "id": str(event.id),
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": str(event.resource_id) if event.resource_id else None,
                "user": event.user.display_name if event.user else "System",
                "metadata": event.metadata_,
                "created_at": event.created_at.isoformat(),
            }
            for event in result.scalars().all()
        ]
    }
