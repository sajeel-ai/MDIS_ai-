"""AI Operations & Pipeline Telemetry Domain Service."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from app.models import (
    ProcessingJob,
    ProcessingStep,
    ValidationResult,
    Document,
    ClinicalEntity,
    ReviewTask,
    Extraction,
)


class AIOperationsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _compute_ocr_success_rate(self, eval_report: dict | None) -> float | None:
        """Compute OCR success rate from processing steps or fallback to stored eval."""
        # 1. From live ProcessingStep records
        try:
            completed_res = await self.session.execute(
                select(func.count())
                .select_from(ProcessingStep)
                .where(ProcessingStep.step_name == "ocr", ProcessingStep.status == "completed")
            )
            completed_ocr = completed_res.scalar() or 0

            total_res = await self.session.execute(
                select(func.count())
                .select_from(ProcessingStep)
                .where(ProcessingStep.step_name == "ocr", ProcessingStep.status.in_(["completed", "failed"]))
            )
            total_ocr = total_res.scalar() or 0

            if total_ocr > 0:
                return round(float(completed_ocr) / float(total_ocr), 3)
        except Exception:
            pass

        # 2. Fallback to latest eval results
        if eval_report and isinstance(eval_report, dict):
            mean_cer = eval_report.get("mean_cer")
            if mean_cer is not None:
                return round(max(0.0, 1.0 - float(mean_cer)), 3)

        return None

    async def _compute_extraction_accuracy(self, eval_report: dict | None) -> tuple[float | None, str]:
        """Return a measured value and label that describes its actual source."""
        # 1. From human reviewer decisions
        try:
            approved_res = await self.session.execute(
                select(func.count())
                .select_from(ReviewTask)
                .where(ReviewTask.status == "approved")
            )
            approved = approved_res.scalar() or 0

            reviewed_res = await self.session.execute(
                select(func.count())
                .select_from(ReviewTask)
                .where(ReviewTask.status.in_(["approved", "rejected", "corrected"]))
            )
            total_reviewed = reviewed_res.scalar() or 0

            if total_reviewed > 0:
                reviewer_accuracy = float(approved) / float(total_reviewed)
                return round(reviewer_accuracy, 3), "Reviewer acceptance rate"
        except Exception:
            pass

        # 2. Fallback to stored eval benchmark metrics
        if eval_report and isinstance(eval_report, dict) and eval_report.get("labelled_eval_set") is True:
            assertion_acc = eval_report.get("assertion_accuracy")
            f1_cats = eval_report.get("f1_by_category", {})
            f1_unspecified = f1_cats.get("unspecified") if isinstance(f1_cats, dict) else None

            if assertion_acc is not None and f1_unspecified is not None:
                return round((float(assertion_acc) + float(f1_unspecified)) / 2.0, 3), "Labelled evaluation accuracy"
            if assertion_acc is not None:
                return round(float(assertion_acc), 3), "Labelled evaluation accuracy"
            if f1_unspecified is not None:
                return round(float(f1_unspecified), 3), "Labelled evaluation F1"

        return None, "Not measured"

    async def _compute_confidence_drift(self) -> dict:
        """Compute drift indicator comparing weekly confidence distribution."""
        try:
            now = datetime.now(timezone.utc)
            seven_days_ago = now - timedelta(days=7)

            recent_res = await self.session.execute(
                select(func.avg(ClinicalEntity.confidence))
                .select_from(ClinicalEntity)
                .join(Extraction, ClinicalEntity.extraction_id == Extraction.id)
                .where(Extraction.created_at >= seven_days_ago)
            )
            recent_conf = recent_res.scalar()

            older_res = await self.session.execute(
                select(func.avg(ClinicalEntity.confidence))
                .select_from(ClinicalEntity)
                .join(Extraction, ClinicalEntity.extraction_id == Extraction.id)
                .where(Extraction.created_at < seven_days_ago)
            )
            older_conf = older_res.scalar()

            if recent_conf is not None and older_conf is not None:
                delta = round(float(recent_conf) - float(older_conf), 4)
                if delta < -0.05:
                    status = "drift_detected"
                elif delta > 0.02:
                    status = "improving"
                else:
                    status = "stable"
                return {"drift": delta, "status": status}
        except Exception:
            pass

        return {"drift": None, "status": "not_measured"}

    async def get_aiops_metrics(self) -> dict:
        total_jobs_res = await self.session.execute(select(func.count()).select_from(ProcessingJob))
        total_jobs = total_jobs_res.scalar() or 0

        running_jobs_res = await self.session.execute(
            select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status == "running")
        )
        running_jobs = running_jobs_res.scalar() or 0

        failed_jobs_res = await self.session.execute(
            select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status == "failed")
        )
        failed_jobs = failed_jobs_res.scalar() or 0

        completed_jobs_res = await self.session.execute(
            select(func.count()).select_from(ProcessingJob).where(ProcessingJob.status == "completed")
        )
        completed_jobs = completed_jobs_res.scalar() or 0

        avg_time_res = await self.session.execute(
            select(func.avg(ProcessingJob.processing_ms)).where(ProcessingJob.status == "completed")
        )
        avg_processing_ms = avg_time_res.scalar()

        avg_conf_res = await self.session.execute(select(func.avg(ClinicalEntity.confidence)))
        avg_confidence = avg_conf_res.scalar()
        eval_report = self._latest_eval_report()

        ocr_rate = await self._compute_ocr_success_rate(eval_report)
        extraction_acc, extraction_label = await self._compute_extraction_accuracy(eval_report)
        drift_data = await self._compute_confidence_drift()

        return {
            "total_jobs": total_jobs,
            "running_jobs": running_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "avg_processing_ms": int(avg_processing_ms) if avg_processing_ms is not None else None,
            "avg_processing_sec": (round(float(avg_processing_ms) / 1000.0, 2) if avg_processing_ms is not None else None),
            "avg_confidence": (round(float(avg_confidence), 3) if avg_confidence is not None else None),
            "ocr_success_rate": ocr_rate,
            "extraction_accuracy": extraction_acc,
            "extraction_accuracy_label": extraction_label,
            "confidence_drift": drift_data.get("drift"),
            "drift_status": drift_data.get("status", "not_measured"),
            "latest_eval": eval_report,
        }

    @staticmethod
    def _latest_eval_report() -> dict | None:
        report_path = Path(__file__).resolve().parents[3] / "evals" / "latest_eval.json"
        if not report_path.is_file():
            return None
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(report, dict) or not isinstance(report.get("fixtures_evaluated"), int):
            return None
        return report

    async def get_recent_jobs(self, limit: int = 20) -> list[dict]:
        query = select(ProcessingJob).options(
            selectinload(ProcessingJob.document),
            selectinload(ProcessingJob.steps),
        ).order_by(desc(ProcessingJob.created_at)).limit(limit)

        res = await self.session.execute(query)
        jobs = res.scalars().all()

        items = []
        for j in jobs:
            doc = j.document
            items.append({
                "job_id": str(j.id),
                "document_id": str(j.document_id),
                "case_id": f"CL-{str(j.document_id)[:6].upper()}",
                "doc_type": doc.document_type if doc else "Discharge Summary",
                "pipeline_version": j.pipeline_version or "v1.4.2",
                "status": j.status,
                "created_at": j.created_at.isoformat(),
                "processing_ms": j.processing_ms,
                "step_count": len(j.steps),
                "warning_count": j.warning_count,
            })
        return items
