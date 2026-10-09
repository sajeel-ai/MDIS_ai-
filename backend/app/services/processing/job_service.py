"""Processing job lifecycle service."""

import uuid
from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ClinicalEntity,
    Document,
    EvidenceSpan,
    Extraction,
    ProcessingJob,
    ReviewTask,
    ValidationResult,
)
from app.providers.extraction import validate_extraction_provider_configuration
from app.workflows.clinical_processing import ClinicalProcessingWorkflow


ACTIVE_JOB_STATUSES = ("queued", "running")


class ProcessingConflictError(ValueError):
    """The document's current lifecycle does not allow this processing action."""


@dataclass
class ProcessingJobRequest:
    job: ProcessingJob
    created: bool


class JobService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_and_enqueue_job(self, document_id: uuid.UUID) -> ProcessingJobRequest:
        """Return the existing state for duplicates; create only for fresh uploads."""
        doc = await self._get_document_for_update(document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        active_job = await self._get_active_job(document_id)
        if active_job:
            return ProcessingJobRequest(active_job, created=False)

        latest_job = await self._get_latest_job(document_id)
        if latest_job and latest_job.status in ("completed", "failed", "cancelled"):
            return ProcessingJobRequest(latest_job, created=False)
        if doc.status in ("completed", "failed"):
            raise ProcessingConflictError(
                f"Document is {doc.status}; use the explicit retry endpoint for a failed document"
            )

        return await self._create_job(doc)

    async def retry_failed_job(self, document_id: uuid.UUID) -> ProcessingJobRequest:
        """Explicitly retry the latest failed/cancelled run after removing its partial output."""
        doc = await self._get_document_for_update(document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        active_job = await self._get_active_job(document_id)
        if active_job:
            return ProcessingJobRequest(active_job, created=False)

        latest_job = await self._get_latest_job(document_id)
        if not latest_job or latest_job.status not in ("failed", "cancelled"):
            raise ProcessingConflictError("Only a failed or cancelled processing job can be retried")

        # A failed workflow can have flushed partial results before it marked the
        # job failed. Remove only artifacts owned by that failed run so a retry
        # cannot leave duplicate entities, evidence, validation, or review tasks.
        entity_ids = select(ClinicalEntity.id).join(Extraction).where(
            Extraction.processing_job_id == latest_job.id
        )
        await self.session.execute(delete(ReviewTask).where(ReviewTask.entity_id.in_(entity_ids)))
        await self.session.execute(delete(EvidenceSpan).where(EvidenceSpan.entity_id.in_(entity_ids)))
        await self.session.execute(delete(ValidationResult).where(ValidationResult.entity_id.in_(entity_ids)))
        await self.session.execute(delete(ClinicalEntity).where(ClinicalEntity.id.in_(entity_ids)))
        await self.session.execute(
            delete(Extraction).where(Extraction.processing_job_id == latest_job.id)
        )

        return await self._create_job(doc)

    async def reprocess_document(self, document_id: uuid.UUID) -> ProcessingJobRequest:
        """Start a fresh extraction run, replacing previous extracted output."""
        doc = await self._get_document_for_update(document_id)
        if not doc:
            raise ValueError(f"Document {document_id} not found")
        active_job = await self._get_active_job(document_id)
        if active_job:
            return ProcessingJobRequest(active_job, created=False)

        entity_ids = select(ClinicalEntity.id).join(Extraction).where(
            Extraction.document_id == document_id
        )
        await self.session.execute(delete(ReviewTask).where(ReviewTask.entity_id.in_(entity_ids)))
        await self.session.execute(delete(EvidenceSpan).where(EvidenceSpan.entity_id.in_(entity_ids)))
        await self.session.execute(delete(ValidationResult).where(ValidationResult.entity_id.in_(entity_ids)))
        await self.session.execute(delete(ClinicalEntity).where(ClinicalEntity.id.in_(entity_ids)))
        await self.session.execute(delete(Extraction).where(Extraction.document_id == document_id))
        await self.session.flush()
        return await self._create_job(doc)

    async def _create_job(self, doc: Document) -> ProcessingJobRequest:
        # Do not reject an idempotent request because provider settings changed
        # after its existing job was accepted.
        validate_extraction_provider_configuration()
        job = ProcessingJob(
            document_id=doc.id,
            pipeline_version="v1.4.2",
            status="queued",
        )
        self.session.add(job)
        doc.status = "queued"
        try:
            await self.session.commit()
        except IntegrityError:
            # The partial unique index is the final guard when concurrent
            # requests race despite the row lock.
            await self.session.rollback()
            active_job = await self._get_active_job(doc.id)
            if active_job:
                return ProcessingJobRequest(active_job, created=False)
            raise
        return ProcessingJobRequest(job, created=True)

    async def _get_document_for_update(self, document_id: uuid.UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        return result.scalars().first()

    async def _get_active_job(self, document_id: uuid.UUID) -> ProcessingJob | None:
        result = await self.session.execute(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(ProcessingJob.created_at.desc())
        )
        return result.scalars().first()

    async def _get_latest_job(self, document_id: uuid.UUID) -> ProcessingJob | None:
        result = await self.session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def run_job_workflow(self, job_id: uuid.UUID) -> ProcessingJob:
        workflow = ClinicalProcessingWorkflow(self.session)
        return await workflow.execute_job(job_id)

    async def get_job_status(self, job_id: uuid.UUID) -> Dict[str, Any] | None:
        res = await self.session.execute(
            select(ProcessingJob)
            .options(selectinload(ProcessingJob.steps))
            .where(ProcessingJob.id == job_id)
        )
        job = res.scalars().first()
        if not job:
            return None

        steps_data = [
            {
                "id": str(s.id),
                "step_name": s.step_name,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "processing_ms": s.processing_ms,
                "model_version": s.model_version,
                "error_code": s.error_code,
                "error_message": s.error_message,
            }
            for s in job.steps
        ]

        return {
            "job_id": str(job.id),
            "document_id": str(job.document_id),
            "status": job.status,
            "pipeline_version": job.pipeline_version,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "processing_ms": job.processing_ms,
            "warning_count": job.warning_count,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "steps": steps_data,
        }
