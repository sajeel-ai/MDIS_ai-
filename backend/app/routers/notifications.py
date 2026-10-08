"""Authenticated, organization-scoped notification summaries."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.models import Document, ReviewTask

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_roles(*tuple(UserRole)))],
)


@router.get("")
async def get_notifications(
    current_user: UserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Return lightweight pending-review alerts without clinical text."""
    organization_id = current_user.organization_id
    if organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access required")

    filters = (
        Document.organization_id == organization_id,
        Document.source.in_(["UserUpload", "upload"]),
        ReviewTask.status == "pending",
    )
    pending_count = await db.scalar(
        select(func.count(ReviewTask.id))
        .join(Document, ReviewTask.document_id == Document.id)
        .where(*filters)
    )
    result = await db.execute(
        select(ReviewTask, Document.document_type)
        .join(Document, ReviewTask.document_id == Document.id)
        .where(*filters)
        .order_by(desc(ReviewTask.created_at))
        .limit(5)
    )
    items = [
        {
            "id": str(task.id),
            "priority": task.priority,
            "created_at": task.created_at.isoformat(),
            "document_type": document_type,
        }
        for task, document_type in result.all()
    ]
    return {"pending_count": pending_count or 0, "items": items}
