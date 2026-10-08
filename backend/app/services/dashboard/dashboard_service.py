"""Dashboard Domain Service — Calculates real PostgreSQL metrics."""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import Document, ReviewTask, Extraction, ClinicalEntity, Patient, ValidationResult
from app.config import settings



class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_dashboard_data(self) -> dict:
        # Total documents count
        doc_count_res = await self.session.execute(select(func.count()).select_from(Document))
        total_documents = doc_count_res.scalar() or 0

        # Processed count
        proc_count_res = await self.session.execute(
            select(func.count()).select_from(Document).where(Document.status == "completed")
        )
        processed = proc_count_res.scalar() or 0

        # Pending review count
        pending_res = await self.session.execute(
            select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "pending")
        )
        pending_review = pending_res.scalar() or 0

        # Failed count
        failed_res = await self.session.execute(
            select(func.count()).select_from(Document).where(Document.status == "failed")
        )
        failed = failed_res.scalar() or 0

        success_rate = (processed / total_documents) if total_documents > 0 else None

        # Priority breakdown
        hp_res = await self.session.execute(
            select(func.count()).select_from(ReviewTask).where(
                ReviewTask.status == "pending", ReviewTask.priority == "high"
            )
        )
        high_priority = hp_res.scalar() or 0

        mp_res = await self.session.execute(
            select(func.count()).select_from(ReviewTask).where(
                ReviewTask.status == "pending", ReviewTask.priority == "medium"
            )
        )
        medium_priority = mp_res.scalar() or 0

        standard = max(0, pending_review - high_priority - medium_priority)
        conflict_res = await self.session.execute(
            select(func.count()).select_from(ValidationResult).where(
                ValidationResult.rule_code == "CONFLICT",
                ValidationResult.severity.in_(["warning", "error"]),
            )
        )
        ai_conflicts = conflict_res.scalar() or 0

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
                select(func.avg(ClinicalEntity.confidence)).where(
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
                            ent.confidence is not None and float(ent.confidence) >= 0.65
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
            },
            "extraction_quality": extraction_quality,
            "recent_cases": recent_cases,
        }
