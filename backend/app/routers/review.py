"""Review Center API Router."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.schemas.common import PaginatedResponse
from app.schemas.review import ReviewTaskResponse, ReviewDecisionRequest
from app.services.review.review_service import ReviewService
from app.services.audit_service import record_audit_event
from app.config import settings
from sqlalchemy import select
from app.models import Document

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(require_roles(*tuple(UserRole)))])


@router.get("/policy")
async def get_review_policy():
    return {
        "policy": settings.review_policy,
        "confidence_threshold": settings.review_confidence_threshold,
        "high_priority_threshold": settings.review_high_priority_threshold,
    }


@router.post("/documents/{document_id}/approve-clean", dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def approve_clean_review_items(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    document = await db.scalar(
        select(Document.id).where(
            Document.id == document_id,
            Document.organization_id == current_user.organization_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    approved_count = await ReviewService(db).approve_clean_for_document(
        document_id, current_user.id, current_user.organization_id
    )
    return {"approved_count": approved_count}


@router.get("", response_model=PaginatedResponse[ReviewTaskResponse])
@router.get("/queue", response_model=PaginatedResponse[ReviewTaskResponse])
async def get_review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    priority: Optional[str] = None,
    task_status: Optional[str] = Query("pending", alias="status"),
    search: Optional[str] = None,
    document_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(
        db, action="view_review_queue", user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    service = ReviewService(db)
    items, total = await service.get_review_queue(
        page=page,
        page_size=page_size,
        priority=priority,
        status=task_status,
        search=search,
        document_id=document_id,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


@router.get("/stats")
async def get_review_stats(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(
        db, action="view_review_stats", user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    service = ReviewService(db)
    return await service.get_review_stats()


@router.get("/{task_id}", response_model=ReviewTaskResponse)
async def get_review_task_detail(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(
        db, action="view_review_task", user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="review_task", resource_id=task_id,
    )
    service = ReviewService(db)
    try:
        return await service.get_review_task_detail(task_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post("/{task_id}/start", response_model=ReviewTaskResponse, dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def start_review_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = ReviewService(db)
    try:
        return await service.start_review(task_id, reviewer_user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post("/{task_id}/decision", response_model=ReviewTaskResponse, dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def submit_review_decision(
    task_id: uuid.UUID,
    payload: ReviewDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    service = ReviewService(db)
    reviewer_id = current_user.id

    try:
        return await service.record_review_decision(
            task_id=task_id,
            decision=payload.decision,
            comment=payload.comment,
            corrected_value=payload.corrected_value,
            reviewer_user_id=reviewer_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/{task_id}/approve", response_model=ReviewTaskResponse, dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def approve_review_task(
    task_id: uuid.UUID,
    comment: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    return await submit_review_decision(
        task_id=task_id,
        payload=ReviewDecisionRequest(decision="approved", comment=comment),
        db=db,
        current_user=current_user,
    )


@router.post("/{task_id}/reject", response_model=ReviewTaskResponse, dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def reject_review_task(
    task_id: uuid.UUID,
    reason: Optional[str] = Query(None, alias="reason"),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    return await submit_review_decision(
        task_id=task_id,
        payload=ReviewDecisionRequest(decision="rejected", comment=reason),
        db=db,
        current_user=current_user,
    )


@router.post("/{task_id}/correct", response_model=ReviewTaskResponse, dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def correct_review_task(
    task_id: uuid.UUID,
    corrected_value: str = Query(...),
    comment: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    return await submit_review_decision(
        task_id=task_id,
        payload=ReviewDecisionRequest(
            decision="corrected", comment=comment, corrected_value=corrected_value
        ),
        db=db,
        current_user=current_user,
    )
