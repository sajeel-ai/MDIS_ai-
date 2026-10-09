"""Clinical Processing Workflow Orchestrator.

Orchestrates OCR, LLM clinical extraction, normalization, evidence linking,
clinical validation, and review task routing into PostgreSQL records.
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ClinicalEntity,
    Document,
    DocumentVersion,
    EvidenceSpan,
    Extraction,
    ProcessingJob,
    ProcessingStep,
    ReviewTask,
    User,
    ValidationResult,
)
from app.providers.extraction import (
    ExtractionProviderConfigurationError,
    get_extraction_provider,
)
from app.providers.extraction.base import ExtractionProviderFailure
from app.providers.extraction.context import detect_section
from app.schemas.entity_contract import validate_entity_candidates, verify_or_relocate_evidence
from app.providers.ocr import get_ocr_provider
from app.providers.storage import get_storage_provider
from app.config import settings
from app.services.validation.engine import validate_entities
from app.services.validation.review_policy import requires_review
from app.workflows.states import PROCESSING_STEP_STATUSES

logger = logging.getLogger(__name__)


class ClinicalProcessingWorkflow:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ocr_provider = None
        self.extraction_provider = None
        self.storage_provider = None

    async def execute_job(self, job_id: uuid.UUID) -> ProcessingJob:
        res = await self.session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .with_for_update()
        )
        job = res.scalars().first()
        if not job:
            raise ValueError(f"ProcessingJob {job_id} not found")

        # A job may be delivered more than once by the background runner. Only
        # the queued-to-running transition is allowed to execute the workflow.
        if job.status != "queued":
            return job

        doc_res = await self.session.execute(
            select(Document).where(Document.id == job.document_id)
        )
        doc = doc_res.scalars().first()
        if not doc:
            raise ValueError(f"Document {job.document_id} not found")
        self.session.info["organization_id"] = doc.organization_id

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        doc.status = "processing"
        await self.session.commit()

        start_time = time.time()

        try:
            # Provider construction is part of the tracked workflow so an
            # unexpected configuration failure also fails the job explicitly.
            provider_step = await self._record_step(job.id, "provider_initialization", "running")
            self.ocr_provider = self.ocr_provider or get_ocr_provider()
            self.extraction_provider = self.extraction_provider or get_extraction_provider()
            self.storage_provider = self.storage_provider or get_storage_provider()
            await self._complete_step(provider_step, "completed", 0)

            # Step 1: Upload Validation / Read stored file
            step1 = await self._record_step(job.id, "upload_validation", "running")
            if not doc.storage_key:
                raise RuntimeError("PROCESSING_INPUT_MISSING: document has no storage key")
            try:
                file_bytes = await self.storage_provider.read_file(doc.storage_key)
            except Exception as exc:
                raise RuntimeError(
                    "PROCESSING_INPUT_UNREADABLE: unable to read stored document"
                ) from exc
            if not file_bytes:
                raise RuntimeError("PROCESSING_INPUT_EMPTY: stored document is empty")
            await self._complete_step(step1, "completed", 50)

            # Step 2: OCR Processing
            step2 = await self._record_step(job.id, "ocr", "running")
            ocr_res = await self.ocr_provider.extract_text(file_bytes, doc.mime_type)
            await self._complete_step(step2, "completed", 150)

            # Record DocumentVersion
            ver_res = await self.session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.version_number.desc())
            )
            prior_versions = ver_res.scalars().all()

            raw_text = ocr_res.get("text", "")
            if not raw_text.strip():
                raise RuntimeError("OCR_EMPTY_RESULT: OCR produced no usable text")

            text_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

            # OCR retries that produce the same source text reuse the existing
            # provenance version instead of creating duplicate versions.
            doc_version = next(
                (version for version in prior_versions if version.text_hash == text_hash),
                None,
            )
            if doc_version is None:
                latest_version = prior_versions[0] if prior_versions else None
                version_num = (latest_version.version_number + 1) if latest_version else 1
                doc_version = DocumentVersion(
                    document_id=doc.id,
                    version_number=version_num,
                    raw_text=raw_text,
                    text_hash=text_hash,
                    page_count=ocr_res.get("page_count", 0),
                )
                self.session.add(doc_version)
                await self.session.flush()

            # Step 3: Text Normalization
            step3 = await self._record_step(job.id, "text_normalization", "running")
            normalized_text = raw_text.strip()
            await self._complete_step(step3, "completed", 60)

            # Step 4: Clinical NLP / LLM Extraction
            step4 = await self._record_step(job.id, "clinical_extraction", "running")
            ext_res = await self.extraction_provider.extract_clinical_entities(normalized_text)
            await self._complete_step(step4, "completed", 500, model_version=ext_res["model_version"])

            validated_entities, rejected_entities = validate_entity_candidates(
                ext_res.get("entities", [])
            )
            validation_issues = validate_entities(normalized_text, validated_entities)

            extraction = Extraction(
                document_id=doc.id,
                processing_job_id=job.id,
                model_name=ext_res["model_name"],
                model_version=ext_res["model_version"],
                status="completed",
                rejected_entities=rejected_entities,
            )
            self.session.add(extraction)
            await self.session.flush()

            # Step 5 & 6: Entity Normalization & Evidence Linking
            step5 = await self._record_step(job.id, "entity_normalization", "running")
            step6 = await self._record_step(job.id, "evidence_linking", "running")

            entities_created = []
            review_entities = []

            for item in validated_entities:
                item, evidence_verified = verify_or_relocate_evidence(normalized_text, item)

                section = detect_section(normalized_text, item.start_offset) or item.section
                conf = item.confidence

                details_dict = {}
                if item.code:
                    details_dict["code"] = item.code
                if item.code_system:
                    details_dict["code_system"] = item.code_system.value
                details_dict.update(item.details)
                if not evidence_verified:
                    details_dict["evidence_unverified"] = True

                entity = ClinicalEntity(
                    extraction_id=extraction.id,
                    entity_type=item.type.value,
                    raw_text=item.raw_text,
                    normalized_value=item.normalized_value,
                    original_ai_value=item.normalized_value,
                    confidence=conf,
                    status="unreviewed" if evidence_verified else "needs_correction",
                    assertion=item.assertion.value,
                    section=section,
                    details=details_dict if details_dict else None,
                )
                self.session.add(entity)
                await self.session.flush()
                entities_created.append(entity)

                review_entities.append((entity, evidence_verified))

                if evidence_verified:
                    span = EvidenceSpan(
                        entity_id=entity.id,
                        document_version_id=doc_version.id,
                        page_number=item.page_number,
                        start_offset=item.start_offset,
                        end_offset=item.end_offset,
                        text=item.evidence_text,
                    )
                    self.session.add(span)
            await self._complete_step(step5, "completed", 120)
            await self._complete_step(step6, "completed", 80)

            # Step 7: Validation Engine
            step7 = await self._record_step(job.id, "validation", "running")

            for ent, issues in zip(entities_created, validation_issues):
                for issue in issues:
                    self.session.add(ValidationResult(
                        entity_id=ent.id,
                        validation_rule=issue.rule_code,
                        rule_code=issue.rule_code,
                        status="fail" if issue.severity == "error" else "warning",
                        severity=issue.severity,
                        message=issue.message,
                    ))

            job.warning_count = len(rejected_entities) + sum(
                len(issues) for issues in validation_issues
            )

            await self._complete_step(step7, "completed", 100)

            # Step 8: Review Routing
            step8 = await self._record_step(job.id, "review_routing", "running")

            # Select authorized clinical reviewer / admin user
            reviewer_user_res = await self.session.execute(
                select(User)
                .where(
                    User.is_active == True,
                    User.role.in_(
                        ["admin", "clinical_reviewer", "reviewer", "clinician"]
                    ),
                )
                .limit(1)
            )
            reviewer_user = reviewer_user_res.scalars().first()

            review_task_count = 0
            if review_entities:
                for (review_ent, evidence_verified), issues in zip(review_entities, validation_issues):
                    if not requires_review(review_ent, issues):
                        continue
                    has_rule_findings = any(i.severity in {"warning", "error"} for i in issues)
                    priority = (
                        "high" if review_ent.confidence < settings.review_high_priority_threshold
                        else "medium" if review_ent.confidence < settings.review_confidence_threshold
                        else "normal"
                    )
                    reason = (
                        "Validation rules require review: " + ", ".join(i.rule_code for i in issues)
                        if has_rule_findings
                        else f"High priority review: model confidence ({review_ent.confidence:.2f}) is below configured threshold"
                        if review_ent.confidence < settings.review_high_priority_threshold
                        else (
                            f"Human review required: model confidence ({review_ent.confidence:.2f}) is below configured threshold"
                            if review_ent.confidence < settings.review_confidence_threshold
                            else "Human review required for non-present assertion"
                            if review_ent.assertion != "present"
                            else "Medication entities always require review"
                            if review_ent.entity_type == "medication"
                        else "Evidence could not be verified; review required"
                        if not evidence_verified
                        else "Human verification required after clinical extraction"
                        )
                    )
                    review_task = ReviewTask(
                        document_id=doc.id,
                        entity_id=review_ent.id,
                        assigned_to=reviewer_user.id if reviewer_user else None,
                        status="pending",
                        priority=priority,
                        reason=reason,
                    )
                    self.session.add(review_task)
                    review_task_count += 1
                doc.status = "completed"
                doc.review_status = "pending" if review_task_count else "not_required"
            else:
                doc.status = "completed"
                doc.review_status = "not_required"

            await self._complete_step(step8, "completed", 50)

            # Job Completion
            elapsed_ms = int((time.time() - start_time) * 1000)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.processing_ms = elapsed_ms

            await self.session.commit()
            return job

        except Exception as exc:
            logger.error("Processing job failed job_id=%s error_type=%s", job.id, type(exc).__name__)
            candidate_code = str(exc).partition(":")[0]
            known_error_codes = {
                "OCR_INPUT_EMPTY",
                "OCR_UNSUPPORTED_FORMAT",
                "OCR_FAILED",
                "OCR_IMAGE_PROCESSING_FAILED",
                "OCR_PDF_PROCESSING_FAILED",
                "TESSERACT_NOT_INSTALLED",
                "PROCESSING_INPUT_MISSING",
                "EXTRACTION_FAILED",
                "PROVIDER_CONFIGURATION_ERROR",
                "EXTRACTION_REFUSED",
                "EXTRACTION_TRUNCATED",
                "EXTRACTION_SCHEMA_ERROR",
            }
            error_code = (
                "PROVIDER_CONFIGURATION_ERROR"
                if isinstance(exc, ExtractionProviderConfigurationError)
                else exc.code if isinstance(exc, ExtractionProviderFailure)
                else candidate_code if candidate_code in known_error_codes else "PROCESSING_ERROR"
            )
            error_message = "Processing failed. See error code for details."
            failed_at = datetime.now(timezone.utc)
            running_steps_res = await self.session.execute(
                select(ProcessingStep).where(
                    ProcessingStep.processing_job_id == job.id,
                    ProcessingStep.status == "running",
                )
            )
            for step in running_steps_res.scalars().all():
                step.status = "failed"
                step.completed_at = failed_at
                step.error_code = error_code
                step.error_message = error_message
            job.status = "failed"
            job.completed_at = failed_at
            job.error_code = error_code
            job.error_message = error_message
            doc.status = "failed"
            await self.session.commit()
            raise

    async def _record_step(self, job_id: uuid.UUID, step_name: str, status: str) -> ProcessingStep:
        if status not in PROCESSING_STEP_STATUSES:
            raise ValueError(f"Invalid processing step status: {status}")
        step = ProcessingStep(
            processing_job_id=job_id,
            step_name=step_name,
            status=status,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(step)
        await self.session.flush()
        return step

    async def _complete_step(self, step: ProcessingStep, status: str, ms: int, model_version: str | None = None):
        if status not in PROCESSING_STEP_STATUSES:
            raise ValueError(f"Invalid processing step status: {status}")
        step.status = status
        step.completed_at = datetime.now(timezone.utc)
        step.processing_ms = ms
        if model_version:
            step.model_version = model_version
        await self.session.flush()
