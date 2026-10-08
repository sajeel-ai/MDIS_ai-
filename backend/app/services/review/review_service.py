"""Review Domain Service — Review Queue and Decision Workflows."""

import uuid
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.models import (
    ReviewTask,
    Document,
    Patient,
    Extraction,
    ClinicalEntity,
    EvidenceSpan,
    ValidationResult,
)
from app.workflows.states import aggregate_review_status
from app.services.audit_service import record_audit_event


class ReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _build_task_dict(
        self, task: ReviewTask, include_source_text: bool = False
    ) -> Dict[str, Any]:
        """Format a ReviewTask ORM object into a detailed API response dictionary."""
        doc = task.document
        patient = doc.patient if doc else None

        patient_dict = None
        if patient:
            name_parts = [p for p in [patient.first_name, patient.last_name] if p]
            display_name = " ".join(name_parts) if name_parts else f"Patient {patient.mrn}"
            patient_dict = {
                "id": str(patient.id),
                "display_name": display_name,
                "mrn": patient.mrn or "UNKNOWN",
            }

        doc_dict = None
        if doc:
            doc_dict = {
                "id": str(doc.id),
                "file_name": doc.file_name,
                "document_type": doc.document_type,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }

        # Target entity & evidence
        entity = task.entity
        entity_dict = None
        evidence_dict = None
        validation_dict = None
        validation_results = []

        if entity:
            entity_dict = {
                "id": str(entity.id),
                "type": entity.entity_type,
                "raw_text": entity.raw_text,
                "normalized_value": entity.normalized_value,
                "confidence": float(entity.confidence),
                "assertion": entity.assertion,
                "section": entity.section,
                "status": entity.status,
                "details": entity.details,
                "original_ai_value": entity.original_ai_value,
            }

            if entity.evidence_spans:
                span = entity.evidence_spans[0]
                evidence_dict = {
                    "id": str(span.id),
                    "text": span.text,
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                    "page_number": span.page_number or 1,
                }

            validation_results = [{
                "rule_code": val.rule_code or val.validation_rule.upper(),
                "severity": val.severity,
                "status": val.status,
                "message": val.message,
            } for val in entity.validation_results]
            if validation_results:
                validation_dict = validation_results[0]

        # Source text from latest version
        source_text = None
        if doc and doc.versions:
            latest_version = max(doc.versions, key=lambda v: v.version_number)
            if include_source_text:
                source_text = latest_version.raw_text
            elif evidence_dict and latest_version.raw_text:
                # Provide snippet around evidence if source text not fully requested
                start = max(0, evidence_dict["start_offset"] - 100)
                end = min(len(latest_version.raw_text), evidence_dict["end_offset"] + 100)
                source_text = latest_version.raw_text[start:end]

        if not validation_dict:
            validation_dict = {
                "status": "warning" if task.priority == "high" else "info",
                "message": task.reason or "Automatic validation flag",
            }

        return {
            "id": str(task.id),
            "document_id": str(task.document_id),
            "entity_id": str(task.entity_id) if task.entity_id else None,
            "priority": task.priority,
            "reason": task.reason or "Needs clinical review",
            "status": task.status,
            "assigned_to": str(task.assigned_to) if task.assigned_to else None,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "decision": task.decision,
            "comment": task.comment,
            "document": doc_dict,
            "patient": patient_dict,
            "entity": entity_dict,
            "validation_results": validation_results,
            "evidence": evidence_dict,
            "validation": validation_dict,
            "source_text": source_text,
        }

    async def get_review_queue(
        self,
        page: int = 1,
        page_size: int = 25,
        priority: Optional[str] = None,
        status: Optional[str] = "pending",
        search: Optional[str] = None,
        document_id: Optional[uuid.UUID] = None,
    ) -> Tuple[List[dict], int]:
        query = select(ReviewTask).options(
            selectinload(ReviewTask.document).selectinload(Document.patient),
            selectinload(ReviewTask.document).selectinload(Document.versions),
            selectinload(ReviewTask.entity).selectinload(ClinicalEntity.evidence_spans),
            selectinload(ReviewTask.entity).selectinload(ClinicalEntity.validation_results),
        ).join(ReviewTask.document).where(Document.source.in_(["UserUpload", "upload"]))

        if status:
            if status == "all":
                pass
            else:
                query = query.where(ReviewTask.status == status)

        if priority and priority != "all":
            query = query.where(ReviewTask.priority == priority)

        if document_id:
            query = query.where(ReviewTask.document_id == document_id)

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.outerjoin(Document.patient).outerjoin(ReviewTask.entity)
            query = query.where(
                or_(
                    Document.file_name.ilike(term),
                    Patient.first_name.ilike(term),
                    Patient.last_name.ilike(term),
                    Patient.mrn.ilike(term),
                    ClinicalEntity.raw_text.ilike(term),
                    ClinicalEntity.normalized_value.ilike(term),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total_res = await self.session.execute(count_query)
        total = total_res.scalar() or 0

        offset = (page - 1) * page_size
        query = query.order_by(ReviewTask.created_at.desc()).offset(offset).limit(page_size)
        res = await self.session.execute(query)
        tasks = res.scalars().all()

        items = []
        for t in tasks:
            items.append(await self._build_task_dict(t, include_source_text=False))

        return items, total

    async def get_review_task_detail(self, task_id: uuid.UUID) -> Dict[str, Any]:
        query = (
            select(ReviewTask)
            .options(
                selectinload(ReviewTask.document).selectinload(Document.patient),
                selectinload(ReviewTask.document).selectinload(Document.versions),
                selectinload(ReviewTask.entity).selectinload(ClinicalEntity.evidence_spans),
                selectinload(ReviewTask.entity).selectinload(ClinicalEntity.validation_results),
            )
            .where(ReviewTask.id == task_id)
        )
        res = await self.session.execute(query)
        task = res.scalars().first()
        if not task:
            raise ValueError(f"ReviewTask {task_id} not found")

        return await self._build_task_dict(task, include_source_text=True)

    async def get_review_stats(self) -> Dict[str, int]:
        result = await self.session.execute(
            select(ReviewTask.document_id, ReviewTask.status, ReviewTask.priority)
            .join(ReviewTask.document)
            .where(Document.source.in_(["UserUpload", "upload"]))
        )
        by_document: Dict[uuid.UUID, List[tuple[str, str]]] = {}
        for document_id, task_status, priority in result.all():
            by_document.setdefault(document_id, []).append((task_status, priority))

        pending = sum(
            any(task_status == "pending" for task_status, _ in items)
            for items in by_document.values()
        )
        high_priority = sum(
            any(task_status == "pending" and priority == "high" for task_status, priority in items)
            for items in by_document.values()
        )
        approved = sum(
            bool(items)
            and all(task_status in ("approved", "corrected") for task_status, _ in items)
            for items in by_document.values()
        )
        rejected = sum(
            any(task_status in ("rejected", "corrected", "needs_correction") for task_status, _ in items)
            for items in by_document.values()
        )

        return {
            "pending": pending,
            "high_priority": high_priority,
            "approved": approved,
            "rejected": rejected,
        }

    async def start_review(
        self, task_id: uuid.UUID, reviewer_user_id: uuid.UUID | None = None
    ) -> Dict[str, Any]:
        query = (
            select(ReviewTask)
            .options(selectinload(ReviewTask.document))
            .where(ReviewTask.id == task_id)
        )
        result = await self.session.execute(query)
        task = result.scalars().first()
        if not task:
            raise ValueError(f"ReviewTask {task_id} not found")

        if task.status == "pending":
            now = datetime.now(timezone.utc)
            task.status = "in_review"
            task.started_at = task.started_at or now
            if reviewer_user_id:
                task.assigned_to = reviewer_user_id
            if task.document:
                statuses_res = await self.session.execute(
                    select(ReviewTask.status).where(
                        ReviewTask.document_id == task.document.id
                    )
                )
                task.document.review_status = aggregate_review_status(
                    statuses_res.scalars().all()
                )
            await self.session.commit()

        return await self.get_review_task_detail(task.id)

    async def record_review_decision(
        self,
        task_id: uuid.UUID,
        decision: str,  # approved | rejected | corrected
        comment: str | None = None,
        corrected_value: str | None = None,
        reviewer_user_id: uuid.UUID | None = None,
    ) -> Dict[str, Any]:
        query = (
            select(ReviewTask)
            .options(
                selectinload(ReviewTask.document),
                selectinload(ReviewTask.entity),
            )
            .where(ReviewTask.id == task_id)
        )
        res = await self.session.execute(query)
        task = res.scalars().first()
        if not task:
            raise ValueError(f"ReviewTask {task_id} not found")

        valid_decisions = ["approved", "rejected", "corrected", "needs_correction"]
        if decision not in valid_decisions:
            raise ValueError(f"Invalid decision '{decision}'. Must be one of {valid_decisions}")

        target_status = "approved" if decision == "approved" else ("corrected" if decision in ["corrected", "needs_correction"] else "rejected")

        task.status = target_status
        task.decision = target_status
        task.comment = comment
        task.completed_at = datetime.now(timezone.utc)
        if reviewer_user_id:
            task.assigned_to = reviewer_user_id

        # Update associated ClinicalEntity if linked
        if task.entity:
            entity_res = await self.session.execute(
                select(ClinicalEntity).where(ClinicalEntity.id == task.entity_id)
            )
            entity = entity_res.scalars().first()
            if entity:
                if target_status == "approved":
                    entity.status = "approved"
                elif target_status == "rejected":
                    entity.status = "rejected"
                elif target_status == "corrected":
                    entity.status = "needs_correction"
                    if corrected_value and corrected_value.strip():
                        entity.original_ai_value = entity.original_ai_value or entity.normalized_value
                        entity.normalized_value = corrected_value.strip()

        # Keep processing status independent from the review lifecycle.
        doc_res = await self.session.execute(
            select(Document).where(Document.id == task.document_id)
        )
        doc = doc_res.scalars().first()
        if doc:
            statuses_res = await self.session.execute(
                select(ReviewTask.status).where(ReviewTask.document_id == doc.id)
            )
            doc.review_status = aggregate_review_status(statuses_res.scalars().all())

        await record_audit_event(
            self.session,
            action="review_decision",
            user_id=reviewer_user_id,
            organization_id=doc.organization_id if doc else None,
            resource_type="review_task",
            resource_id=task.id,
        )
        await self.session.commit()

        return await self.get_review_task_detail(task.id)

    async def approve_clean_for_document(self, document_id: uuid.UUID, reviewer_user_id: uuid.UUID | None = None, organization_id: uuid.UUID | None = None) -> int:
        query = (
            select(ReviewTask)
            .options(selectinload(ReviewTask.entity).selectinload(ClinicalEntity.validation_results), selectinload(ReviewTask.document))
            .join(ReviewTask.document)
            .where(ReviewTask.document_id == document_id, ReviewTask.status.in_(["pending", "in_review"]))
        )
        if organization_id is not None:
            query = query.where(Document.organization_id == organization_id)
        result = await self.session.execute(query)
        tasks = result.scalars().all()
        approved = 0
        now = datetime.now(timezone.utc)
        for task in tasks:
            findings = [
                v for v in (task.entity.validation_results if task.entity else [])
                if v.severity in {"warning", "error"} or v.status in {"fail", "warning"}
            ]
            if findings:
                continue
            task.status = task.decision = "approved"
            task.completed_at = now
            if reviewer_user_id:
                task.assigned_to = reviewer_user_id
            if task.entity:
                task.entity.status = "approved"
            approved += 1
        document = tasks[0].document if tasks else None
        if document:
            statuses = await self.session.execute(select(ReviewTask.status).where(ReviewTask.document_id == document_id))
            document.review_status = aggregate_review_status(statuses.scalars().all())
        await record_audit_event(
            self.session, action="approve_clean_review_items", user_id=reviewer_user_id,
            organization_id=document.organization_id if document else None,
            resource_type="document", resource_id=document_id,
        )
        await self.session.commit()
        return approved
