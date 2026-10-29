"""Dashboard Domain Service — Calculates real PostgreSQL metrics."""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import false, select, func
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentValidationFlag, ReviewTask, Extraction, ClinicalEntity, Patient, ValidationResult
from app.config import settings



class DashboardService:
    def __init__(self, session: AsyncSession, organization_id=None):
        self.session = session
        self.organization_id = organization_id

    def _organization_scope(self):
        if self.organization_id is None:
            return false()
        return Document.organization_id == self.organization_id

    async def get_dashboard_data(self) -> dict:
        # Total documents count
        doc_count_res = await self.session.execute(select(func.count()).select_from(Document).where(self._organization_scope()))
        total_documents = doc_count_res.scalar() or 0

        # Processed count
        proc_count_res = await self.session.execute(
            select(func.count()).select_from(Document).where(self._organization_scope(), Document.status == "completed")
        )
        processed = proc_count_res.scalar() or 0

        # Pending review count
        pending_res = await self.session.execute(
            select(func.count()).select_from(ReviewTask).join(Document, Document.id == ReviewTask.document_id).where(
                self._organization_scope(), ReviewTask.status == "pending"
            )
        )
        pending_review = pending_res.scalar() or 0

        # Failed count
        failed_res = await self.session.execute(
            select(func.count()).select_from(Document).where(self._organization_scope(), Document.status == "failed")
        )
        failed = failed_res.scalar() or 0

        success_rate = (processed / total_documents) if total_documents > 0 else None

        # Priority breakdown
        hp_res = await self.session.execute(
            select(func.count()).select_from(ReviewTask).join(Document, Document.id == ReviewTask.document_id).where(
                self._organization_scope(), ReviewTask.status == "pending", ReviewTask.priority == "high"
            )
        )
        high_priority = hp_res.scalar() or 0

        mp_res = await self.session.execute(
            select(func.count()).select_from(ReviewTask).join(Document, Document.id == ReviewTask.document_id).where(
                self._organization_scope(), ReviewTask.status == "pending", ReviewTask.priority == "medium"
            )
        )
        medium_priority = mp_res.scalar() or 0

        standard = max(0, pending_review - high_priority - medium_priority)
        conflict_res = await self.session.execute(
            select(func.count()).select_from(ValidationResult)
            .join(ClinicalEntity, ClinicalEntity.id == ValidationResult.entity_id)
            .join(Extraction, Extraction.id == ClinicalEntity.extraction_id)
            .join(Document, Document.id == Extraction.document_id)
            .where(self._organization_scope(),
                ValidationResult.rule_code == "CONFLICT",
                ValidationResult.severity.in_(["warning", "error"]),
            )
        )
        ai_conflicts = conflict_res.scalar() or 0

        critical_entity_res = await self.session.execute(
            select(func.count()).select_from(ValidationResult)
            .join(ClinicalEntity, ClinicalEntity.id == ValidationResult.entity_id)
            .join(Extraction, Extraction.id == ClinicalEntity.extraction_id)
            .join(Document, Document.id == Extraction.document_id)
            .where(self._organization_scope(),
                ValidationResult.status.in_(["warning", "fail", "error"]),
                (ValidationResult.severity == "critical")
                | (ValidationResult.rule_code.in_(["CRITICAL", "CONFLICT"])),
            )
        )
        critical_document_res = await self.session.execute(
            select(func.count()).select_from(DocumentValidationFlag)
            .join(Document, Document.id == DocumentValidationFlag.document_id)
            .where(self._organization_scope(),
                DocumentValidationFlag.superseded_at.is_(None),
                (DocumentValidationFlag.severity == "critical")
                | (DocumentValidationFlag.rule_code.in_(["CRITICAL", "CONFLICT"])),
            )
        )
        critical_flags = (critical_entity_res.scalar() or 0) + (critical_document_res.scalar() or 0)

        low_confidence_res = await self.session.execute(
            select(func.count())
            .select_from(ReviewTask)
            .join(ClinicalEntity, ClinicalEntity.id == ReviewTask.entity_id)
            .join(Document, Document.id == ReviewTask.document_id)
            .where(
                self._organization_scope(),
                ReviewTask.status == "pending",
                ClinicalEntity.confidence.is_not(None),
                ClinicalEntity.confidence < settings.review_high_priority_threshold,
            )
        )
        low_confidence = low_confidence_res.scalar() or 0

        unavailable_confidence_res = await self.session.execute(
            select(func.count())
            .select_from(ReviewTask)
            .join(ClinicalEntity, ClinicalEntity.id == ReviewTask.entity_id)
            .join(Document, Document.id == ReviewTask.document_id)
            .where(
                self._organization_scope(),
                ReviewTask.status == "pending",
                ClinicalEntity.confidence.is_(None),
            )
        )
        confidence_unavailable = unavailable_confidence_res.scalar() or 0

        approved_res = await self.session.execute(
            select(func.count()).select_from(Document).where(
                self._organization_scope(),
                Document.status == "completed", Document.review_status == "approved"
            )
        )
        approved = approved_res.scalar() or 0

        # Extraction quality by entity type
        quality_types = [
            ("diagnoses", "diagnosis"),
            ("medications", "medication"),
            ("symptoms", "symptom"),
            ("procedures", "procedure"),
            ("labs", "lab"),
        ]
        extraction_quality = []
        for t, db_type in quality_types:
            avg_res = await self.session.execute(
                select(func.avg(ClinicalEntity.confidence))
                .join(Extraction, Extraction.id == ClinicalEntity.extraction_id)
                .join(Document, Document.id == Extraction.document_id)
                .where(
                    self._organization_scope(),
                    ClinicalEntity.entity_type == db_type,
                    ClinicalEntity.assertion == "present",
                    (ClinicalEntity.section != "ALLERGIES") | (ClinicalEntity.section.is_(None)),
                )
            )
            avg_score = avg_res.scalar()
            extraction_quality.append({
                "entity_type": t,
                "model_confidence_uncalibrated": float(avg_score) if avg_score is not None else None,
            })

        # Recent 10 cases
        recent_docs_res = await self.session.execute(
            select(Document)
            .options(
                selectinload(Document.patient),
                selectinload(Document.review_tasks),
                selectinload(Document.extractions).selectinload(Extraction.entities).selectinload(ClinicalEntity.evidence_spans)
            )
            .where(self._organization_scope())
            .order_by(Document.updated_at.desc())
            .limit(10)
        )

        recent_docs = recent_docs_res.scalars().all()

        recent_cases = []
        for d in recent_docs:
            patient_name = (
                " ".join(
                    part
                    for part in [
                        d.patient.first_name if d.patient else None,
                        d.patient.last_name if d.patient else None,
                    ]
                    if part
                )
                if d.patient and (d.patient.first_name or d.patient.last_name)
                else None
            )
            mrn = d.patient.mrn if d.patient else None
            review_status = d.review_status.replace("_", " ").title()

            counts = {"diagnoses": 0, "medications": 0, "symptoms": 0, "procedures": 0}
            if d.extractions:
                for ext in d.extractions:
                    for ent in ext.entities:
                        if ent.assertion != "present" or (
                            ent.entity_type == "medication" and ent.section == "ALLERGIES"
                        ):
                            continue
                        t = ent.entity_type
                        if t == "diagnosis":
                            counts["diagnoses"] += 1
                        elif t == "medication":
                            counts["medications"] += 1
                        elif t == "symptom":
                            counts["symptoms"] += 1
                        elif t == "procedure":
                            counts["procedures"] += 1

            recent_cases.append({
                "id": f"CL-{str(d.id)[:6].upper()}",
                "patient_name": patient_name,
                "mrn": mrn,
                "doc_type": d.document_type,
                "status": d.status,
                "confidence": (
                    "high"
                    if any(
                        ent.confidence is not None and float(ent.confidence) >= settings.review_confidence_threshold
                        and ent.assertion == "present"
                        and not (ent.entity_type == "medication" and ent.section == "ALLERGIES")
                        for ext in d.extractions
                        for ent in ext.entities
                    )
                    else (
                        "medium"
                        if any(
                            ent.confidence is not None and float(ent.confidence) >= settings.review_high_priority_threshold
                            and ent.assertion == "present"
                            and not (ent.entity_type == "medication" and ent.section == "ALLERGIES")
                            for ext in d.extractions
                            for ent in ext.entities
                        )
                        else (
                            "low"
                            if any(
                                ent.confidence is not None
                                and ent.assertion == "present"
                                and not (ent.entity_type == "medication" and ent.section == "ALLERGIES")
                                for ext in d.extractions
                                for ent in ext.entities
                            )
                            else "not_available"
                        )
                    )
                ),
                "review_status": review_status,
                "last_updated": d.updated_at.isoformat(),
                "entity_counts": counts,
            })

        return {
            "metrics": {
                "total_documents": total_documents,
                "processed": processed,
                "pending_review": pending_review,
                "failed": failed,
                "success_rate": round(success_rate, 3) if success_rate is not None else None,
                "last_updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "review_queue_summary": {
                "high_priority": high_priority,
                "medium_priority": medium_priority,
                "standard": standard,
                "ai_conflicts": ai_conflicts,
                "awaiting_review": pending_review,
                "critical_flags": critical_flags,
                "low_confidence": low_confidence,
                "confidence_unavailable": confidence_unavailable,
                "approved": approved,
                "failed": failed,
            },
            "extraction_quality": extraction_quality,
            "recent_cases": recent_cases,
        }
