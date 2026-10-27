"""Review Center API Router."""

import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import UserContext, get_current_user
from app.dependencies.auth import UserRole
from app.dependencies.permissions import require_roles
from app.schemas.common import PaginatedResponse
from app.schemas.review import ReviewTaskResponse, ReviewDecisionRequest
from app.services.review.review_service import ReviewService, ReviewVersionConflict
from app.services.audit_service import record_audit_event
from app.config import settings
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import ClinicalEntity, ClinicalEntityRevision, Document, Extraction, ReviewTask
from app.security.authorization import authorize_document_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"], dependencies=[Depends(require_roles(*tuple(UserRole)))])


class EntityVersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class EntityEditRequest(EntityVersionRequest):
    normalized_value: str | None = None
    assertion: str | None = None
    section: str | None = None


class EntityCommentRequest(EntityVersionRequest):
    comment: str = Field(min_length=1, max_length=4000)


async def _load_scoped_entity(entity_id: uuid.UUID, db: AsyncSession, user: UserContext):
    result = await db.execute(
        select(ClinicalEntity, Document)
        .join(Extraction, ClinicalEntity.extraction_id == Extraction.id)
        .join(Document, Extraction.document_id == Document.id)
        .options(selectinload(ClinicalEntity.evidence_spans), selectinload(ClinicalEntity.validation_results))
        .where(ClinicalEntity.id == entity_id, Document.organization_id == user.organization_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Clinical entity not found")
    return row[0], row[1]


def _entity_snapshot(entity: ClinicalEntity) -> dict:
    return {
        "status": entity.status,
        "normalized_value": entity.normalized_value,
        "assertion": entity.assertion,
        "section": entity.section,
    }


async def _persist_entity_revision(entity, before, actor_id, action, db, request, organization_id, comment=None):
    after = _entity_snapshot(entity)
    db.add(ClinicalEntityRevision(
        entity_id=entity.id, actor_user_id=actor_id, source="reviewer_edited",
        action=action, before=before, after=after, comment=comment,
    ))
    await record_audit_event(
        db, action=f"review_entity_{action}", user_id=actor_id,
        organization_id=organization_id, resource_type="clinical_entity",
        resource_id=entity.id, request=request,
    )
    await db.commit()


@router.post("/entities/{entity_id}/edit", dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def edit_review_entity(
    entity_id: uuid.UUID, payload: EntityEditRequest, request: Request,
    db: AsyncSession = Depends(get_db), current_user: UserContext = Depends(get_current_user),
):
    entity, document = await _load_scoped_entity(entity_id, db, current_user)
    if entity.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Entity changed; reload before editing")
    before = _entity_snapshot(entity)
    if payload.normalized_value is not None:
        if not payload.normalized_value.strip():
            raise HTTPException(status_code=422, detail="Corrected value must not be empty")
        entity.normalized_value = payload.normalized_value.strip()
        entity.original_ai_value = entity.original_ai_value or before["normalized_value"]
    if payload.assertion is not None:
        entity.assertion = payload.assertion
    if payload.section is not None:
        entity.section = payload.section
    entity.status = "needs_correction"
    entity.source = "reviewer_edited"
    entity.version += 1
    await _persist_entity_revision(entity, before, current_user.id, "edited", db, request, document.organization_id)
    return {"entity_id": str(entity.id), "version": entity.version, "status": entity.status}


@router.post("/entities/{entity_id}/reject", dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def reject_review_entity(
    entity_id: uuid.UUID, payload: EntityVersionRequest, request: Request,
    db: AsyncSession = Depends(get_db), current_user: UserContext = Depends(get_current_user),
):
    entity, document = await _load_scoped_entity(entity_id, db, current_user)
    if entity.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Entity changed; reload before rejecting")
    task = await db.scalar(select(ReviewTask).where(ReviewTask.entity_id == entity.id).order_by(ReviewTask.created_at.desc()).limit(1))
    if task is None:
        raise HTTPException(status_code=409, detail="Entity has no review task to reject")
    try:
        return await ReviewService(db).record_review_decision(
            task_id=task.id, decision="rejected", reviewer_user_id=current_user.id,
            expected_version=task.version,
        )
    except ReviewVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/comment", dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def comment_on_review_entity(
    entity_id: uuid.UUID, payload: EntityCommentRequest, request: Request,
    db: AsyncSession = Depends(get_db), current_user: UserContext = Depends(get_current_user),
):
    entity, document = await _load_scoped_entity(entity_id, db, current_user)
    if entity.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Entity changed; reload before commenting")
    before = _entity_snapshot(entity)
    entity.version += 1
    await _persist_entity_revision(entity, before, current_user.id, "commented", db, request, document.organization_id, payload.comment.strip())
    return {"entity_id": str(entity.id), "version": entity.version, "comment_saved": True}


@router.post("/entities/{entity_id}/accept", dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def accept_review_entity(
    entity_id: uuid.UUID, payload: EntityVersionRequest, request: Request,
    db: AsyncSession = Depends(get_db), current_user: UserContext = Depends(get_current_user),
):
    entity, document = await _load_scoped_entity(entity_id, db, current_user)
    if entity.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Entity changed; reload before accepting")
    task = await db.scalar(select(ReviewTask).where(ReviewTask.entity_id == entity.id).order_by(ReviewTask.created_at.desc()).limit(1))
    if task is None:
        raise HTTPException(status_code=409, detail="Entity has no review task to approve")
    try:
        return await ReviewService(db).record_review_decision(
            task_id=task.id, decision="approved", reviewer_user_id=current_user.id,
            expected_version=task.version,
        )
    except ReviewVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/undo", dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def undo_review_entity(
    entity_id: uuid.UUID, payload: EntityVersionRequest, request: Request,
    db: AsyncSession = Depends(get_db), current_user: UserContext = Depends(get_current_user),
):
    entity, document = await _load_scoped_entity(entity_id, db, current_user)
    if entity.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Entity changed; reload before undo")
    if entity.status == "approved":
        raise HTTPException(status_code=409, detail="An approved entity cannot be undone")
    previous = await db.scalar(
        select(ClinicalEntityRevision)
        .where(ClinicalEntityRevision.entity_id == entity.id)
        .order_by(ClinicalEntityRevision.created_at.desc(), ClinicalEntityRevision.id.desc())
        .limit(1)
    )
    if previous is None or previous.before is None:
        raise HTTPException(status_code=409, detail="No prior reviewer revision is available to restore")
    before = _entity_snapshot(entity)
    restored = previous.before
    entity.status = restored.get("status", entity.status)
    entity.normalized_value = restored.get("normalized_value", entity.normalized_value)
    entity.assertion = restored.get("assertion", entity.assertion)
    entity.section = restored.get("section", entity.section)
    entity.source = "reviewer_edited"
    entity.version += 1
    await _persist_entity_revision(entity, before, current_user.id, "undo", db, request, document.organization_id)
    return {"entity_id": str(entity.id), "version": entity.version, "status": entity.status}


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
    request: Request,
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
        resource_type="review_task_collection", request=request,
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
    for item in items:
        await record_audit_event(
            db, action="view_review_task", user_id=current_user.id,
            organization_id=current_user.organization_id, resource_type="review_task",
            resource_id=item.id, request=request,
        )
    await db.commit()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


@router.get("/stats")
async def get_review_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(
        db, action="view_review_stats", user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="review_task_collection", request=request,
    )
    await db.commit()
    service = ReviewService(db)
    return await service.get_review_stats()


@router.get("/{task_id}", response_model=ReviewTaskResponse)
async def get_review_task_detail(
    task_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    await record_audit_event(
        db, action="view_review_task", user_id=current_user.id,
        organization_id=current_user.organization_id,
        resource_type="review_task", resource_id=task_id,
        request=request,
    )
    await db.commit()
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
            acknowledged=bool(payload.acknowledged),
            justification=payload.justification,
            expected_version=payload.expected_version,
        )
    except ReviewVersionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc) else status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception:
        # Keep a failed approval request from poisoning the session or taking
        # down the worker. The client receives a retryable response instead.
        await db.rollback()
        logger.exception("Review decision failed for task %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Review decision could not be saved. Please retry.",
        )


@router.post("/{task_id}/approve", response_model=ReviewTaskResponse, dependencies=[Depends(require_roles(UserRole.REVIEWER, UserRole.ADMIN))])
async def approve_review_task(
    task_id: uuid.UUID,
    comment: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(False),
    justification: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    return await submit_review_decision(
        task_id=task_id,
        payload=ReviewDecisionRequest(
            decision="approved",
            comment=comment,
            acknowledged=acknowledged,
            justification=justification,
        ),
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
