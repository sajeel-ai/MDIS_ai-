"""AI Operations & Pipeline Telemetry Domain Service."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
import json
from pathlib import Path

from app.models import ProcessingJob, ProcessingStep, ValidationResult, Document, ClinicalEntity


class AIOperationsService:
    def __init__(self, session: AsyncSession):
        self.session = session

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

        return {
            "total_jobs": total_jobs,
            "running_jobs": running_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "avg_processing_ms": int(avg_processing_ms) if avg_processing_ms is not None else None,
            "avg_processing_sec": (round(float(avg_processing_ms) / 1000.0, 2) if avg_processing_ms is not None else None),
            "avg_confidence": (round(float(avg_confidence), 3) if avg_confidence is not None else None),
            "ocr_success_rate": None,
            "extraction_accuracy": None,
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
