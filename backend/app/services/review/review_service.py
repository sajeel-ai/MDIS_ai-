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
    DocumentValidationFlag,
    Patient,
    Extraction,
    ClinicalEntity,
    EvidenceSpan,
    ValidationResult,
)
from app.workflows.states import aggregate_review_status
from app.services.audit_service import record_audit_event
from app.config import settings



def evaluate_approval_safety(
    *,
    document: Optional[Document],
    entity: Optional[ClinicalEntity] = None,
    active_doc_flags: Optional[List[DocumentValidationFlag]] = None,
    acknowledged: bool = False,
    justification: Optional[str] = None,
    is_batch: bool = False,
    min_confidence: Optional[float] = None,
    raise_on_violation: bool = False,
) -> Tuple[bool, Optional[str]]:
    """Shared Clinical Safety Gate function for BOTH single and batch approvals.

    Ensures single approval and batch auto-approval cannot diverge.

    Safety rules enforced:
    1. Patient linkage: A document must be linked to a known patient (patient_id is not None).
    2. Document validation flag gate: Active (non-superseded) document-level flags
       with severity warning/error/critical or rule CONFLICT/CRITICAL require manual resolution.
    3. Conflict/Critical flag gate: Any CONFLICT or CRITICAL flag (entity- or document-level)
       cannot be approved while unacknowledged.
    4. Medication / Lab flag override: Overriding MED_DOSE_UNIT, LAB_VALUE_UNIT,
       DRUG_INTERACTION, or ABNORMAL_LAB flags requires a non-empty clinical justification.
    5. Batch-specific gates: Batch approval rejects any entity with validation findings
       (severity warning/error or status fail/warning) or with confidence below threshold.
    """
    def _violation(message: str) -> Tuple[bool, Optional[str]]:
        if raise_on_violation:
            raise ValueError(message)
        return False, message

    # Gate 1: Patient Linkage
    if not document or document.patient_id is None:
        return _violation("Cannot approve review task for a document without a linked patient.")

    doc_flags = list(active_doc_flags or [])
    if not doc_flags and document and "validation_flags" in getattr(document, "__dict__", {}):
        doc_flags = [f for f in document.validation_flags if getattr(f, "superseded_at", None) is None]

    # Gate 2: Document-Level Flags (Batch blocking)
    if is_batch:
        for flag in doc_flags:
            sev = (getattr(flag, "severity", "") or "").lower()
            code = (getattr(flag, "rule_code", "") or "").upper()
            if sev in {"warning", "error", "critical"} or code in {"CONFLICT", "CRITICAL"}:
                return _violation("Document has active validation flags requiring manual review.")

    # Gate 3: Critical / Conflict Flags
    has_conflict = False
    if entity and getattr(entity, "validation_results", None):
        for val in entity.validation_results:
            code = (getattr(val, "rule_code", "") or getattr(val, "validation_rule", "") or "").upper()
            sev = (getattr(val, "severity", "") or "").lower()
            if code in {"CONFLICT", "CRITICAL"} or sev == "critical":
                has_conflict = True
                break
    if not has_conflict:
        for flag in doc_flags:
            code = (getattr(flag, "rule_code", "") or "").upper()
            sev = (getattr(flag, "severity", "") or "").lower()
            if code in {"CONFLICT", "CRITICAL"} or sev == "critical":
                has_conflict = True
                break

    if has_conflict:
        if is_batch:
            return _violation("Entity or document has conflict or critical validation flags.")
        elif not acknowledged:
            return _violation("Cannot approve review task with unacknowledged CONFLICT validation flag.")

    # Gate 4: Medication / Lab / Drug interaction / Abnormal lab override
    med_or_lab_codes = {"MED_DOSE_UNIT", "LAB_VALUE_UNIT", "DRUG_INTERACTION", "ABNORMAL_LAB"}
    has_med_or_lab_flag = False
    if entity and getattr(entity, "validation_results", None):
        for val in entity.validation_results:
            code = (getattr(val, "rule_code", "") or getattr(val, "validation_rule", "") or "").upper()
            if code in med_or_lab_codes:
                has_med_or_lab_flag = True
                break
    if not has_med_or_lab_flag:
        for flag in doc_flags:
            code = (getattr(flag, "rule_code", "") or "").upper()
            if code in med_or_lab_codes:
                has_med_or_lab_flag = True
                break

    if has_med_or_lab_flag:
        if is_batch:
            return _violation("Entity has medication or lab flags requiring clinical override justification.")
        else:
            override_justification = (justification or "").strip()
            if not override_justification:
                return _violation("A non-empty justification is required when overriding a medication or lab validation flag.")

    # Gate 5: Batch-specific Entity Finding & Confidence Gates
    if is_batch and entity:
        findings = [
            v for v in getattr(entity, "validation_results", [])
            if (getattr(v, "severity", "") or "").lower() in {"warning", "error"}
            or (getattr(v, "status", "") or "").lower() in {"fail", "warning"}
        ]
        if findings:
            return _violation("Entity has validation warnings or errors.")

        if entity.confidence is None or (min_confidence is not None and entity.confidence < min_confidence):
            return _violation("Entity confidence is below the required batch approval threshold.")

    return True, None


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
                "review_status": doc.review_status,
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
            "created_at": task.created_at.isoformat() if task.created_at else None,
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
        acknowledged: bool = False,
        justification: str | None = None,
    ) -> Dict[str, Any]:
        query = (
            select(ReviewTask)
            .options(
                selectinload(ReviewTask.document),
                selectinload(ReviewTask.entity).selectinload(ClinicalEntity.validation_results),
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

        # Clinical Safety Gates for Approval — enforced via shared evaluate_approval_safety
        if target_status == "approved":
            active_doc_flags = []
            if task.document and "validation_flags" in getattr(task.document, "__dict__", {}):
                active_doc_flags = [f for f in task.document.validation_flags if getattr(f, "superseded_at", None) is None]
            else:
                doc_flags_res = await self.session.execute(
                    select(DocumentValidationFlag).where(
                        DocumentValidationFlag.document_id == task.document_id,
                        DocumentValidationFlag.superseded_at.is_(None),
                    )
                )
                active_doc_flags = doc_flags_res.scalars().all()

            evaluate_approval_safety(
                document=task.document,
                entity=task.entity,
                active_doc_flags=active_doc_flags,
                acknowledged=acknowledged,
                justification=justification,
                is_batch=False,
                raise_on_violation=True,
            )

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

        audit_metadata: dict[str, Any] = {
            "decision": target_status,
        }
        if comment:
            audit_metadata["comment"] = comment
        override_text = (justification or "").strip()
        if override_text:
            audit_metadata["justification"] = override_text
            audit_metadata["override"] = True
            override_codes = {"MED_DOSE_UNIT", "LAB_VALUE_UNIT", "DRUG_INTERACTION", "ABNORMAL_LAB"}
            overridden_ids = set()
            for validation in getattr(task.entity, "validation_results", []) or []:
                code = (getattr(validation, "rule_code", None) or getattr(validation, "validation_rule", "")).upper()
                if code in override_codes and getattr(validation, "id", None):
                    overridden_ids.add(str(validation.id))
            for flag in active_doc_flags:
                code = (getattr(flag, "rule_code", "") or "").upper()
                if code in override_codes and getattr(flag, "id", None):
                    overridden_ids.add(str(flag.id))
            if overridden_ids:
                audit_metadata["override_flag_ids"] = sorted(overridden_ids)
        if acknowledged:
            audit_metadata["conflict_acknowledged"] = True

        await record_audit_event(
            self.session,
            action="review_decision",
            user_id=reviewer_user_id,
            organization_id=doc.organization_id if doc else None,
            resource_type="review_task",
            resource_id=task.id,
            metadata=audit_metadata,
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

        document = tasks[0].document if tasks else None
        active_doc_flags = []
        if document and "validation_flags" in getattr(document, "__dict__", {}):
            active_doc_flags = [f for f in document.validation_flags if getattr(f, "superseded_at", None) is None]
        else:
            doc_flag_res = await self.session.execute(
                select(DocumentValidationFlag).where(
                    DocumentValidationFlag.document_id == document_id,
                    DocumentValidationFlag.superseded_at.is_(None),
                )
            )
            active_doc_flags = doc_flag_res.scalars().all()

        # Shared safety gate for Document-level batch approval
        doc_allowed, doc_reason = evaluate_approval_safety(
            document=document,
            active_doc_flags=active_doc_flags,
            is_batch=True,
            raise_on_violation=False,
        )
        if not doc_allowed:
            await record_audit_event(
                self.session,
                action="approve_clean_review_items",
                user_id=reviewer_user_id,
                organization_id=document.organization_id if document else None,
                resource_type="document",
                resource_id=document_id,
                metadata={"blocked_reason": doc_reason},
            )
            await self.session.commit()
            return 0

        approved = 0
        now = datetime.now(timezone.utc)
        min_confidence = settings.review_confidence_threshold
        for task in tasks:
            task_allowed, _ = evaluate_approval_safety(
                document=task.document,
                entity=task.entity,
                active_doc_flags=active_doc_flags,
                is_batch=True,
                min_confidence=min_confidence,
                raise_on_violation=False,
            )
            if not task_allowed:
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
