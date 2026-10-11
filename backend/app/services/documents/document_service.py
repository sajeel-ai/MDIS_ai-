"""Document Domain Service."""

import uuid
from pathlib import Path
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, or_
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentVersion, Patient, ProcessingJob, ProcessingStep, Extraction, ClinicalEntity, EvidenceSpan
from app.config import settings
from app.workflows.states import derive_lifecycle_status


class DocumentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upload_document(
        self,
        patient_id: uuid.UUID,
        document_type: str,
        file_bytes: bytes,
        file_name: str,
        mime_type: str | None = None,
        file_path: str | Path | None = None,
        content_hash: str | None = None,
    ) -> dict:
        org_id = self.session.info.get("organization_id")
        patient_query = select(Patient).where(Patient.id == patient_id)
        if org_id is not None:
            patient_query = patient_query.where(Patient.organization_id == org_id)
        pat_res = await self.session.execute(patient_query)
        patient = pat_res.scalars().first()
        if not patient:
            raise ValueError(f"Patient '{patient_id}' not found")

        from app.providers.storage import get_storage_provider
        storage_provider = get_storage_provider()
        storage_key = f"documents/{content_hash or uuid.uuid4().hex}"
        if file_path is not None:
            await storage_provider.save_file_from_path(storage_key, file_path)
        else:
            await storage_provider.save_file(storage_key, file_bytes)

        doc = Document(
            patient_id=patient_id,
            organization_id=patient.organization_id,
            document_type=document_type,
            source="UserUpload",
            file_name=file_name,
            mime_type=mime_type or "application/pdf",
            size_bytes=len(file_bytes),
            storage_key=storage_key,
            status="uploaded",
            review_status="not_required",
        )
        self.session.add(doc)
        await self.session.flush()

        patient_name = (
            " ".join(
                part
                for part in [
                    patient.first_name,
                    f"{patient.last_name[0]}." if patient.last_name else None,
                ]
                if part
            )
            if (patient.first_name or patient.last_name)
            else None
        )
        case_id = f"CL-{str(doc.id)[:6].upper()}"

        await self.session.commit()

        return {
            "id": str(doc.id),
            "case_id": case_id,
            "patient_name": patient_name,
            "mrn": patient.mrn,
            "doc_type": doc.document_type,
            "status": doc.status,
            "review_status": doc.review_status,
            "lifecycle_status": derive_lifecycle_status(doc.status, doc.review_status),
            "confidence": "not_available",
            "last_updated": doc.created_at.isoformat() if doc.created_at else "",
        }

    async def list_documents(
        self,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
        search: str | None = None,
        unlinked_patient: bool = False,
        sort: str = "updated_desc",
        organization_id: uuid.UUID | None = None,
    ) -> Tuple[List[dict], int]:
        query = select(Document).options(
            selectinload(Document.patient),
            selectinload(Document.versions),
            selectinload(Document.extractions).selectinload(Extraction.entities).selectinload(ClinicalEntity.evidence_spans)
        )
        if organization_id is not None:
            query = query.where(Document.organization_id == organization_id)

        if unlinked_patient:
            query = query.where(Document.patient_id.is_(None))

        if status:
            lifecycle_conditions = {
                "failed": Document.status == "failed",
                "processing": Document.status == "processing",
                "uploaded": Document.status.in_(["uploaded", "queued"]),
                "rejected": and_(Document.status == "completed", Document.review_status == "rejected"),
                "approved": and_(Document.status == "completed", Document.review_status == "approved"),
                "in_review": and_(Document.status == "completed", Document.review_status.in_(["pending", "in_review"])),
                "extracted": and_(Document.status == "completed", Document.review_status == "not_required"),
            }
            condition = lifecycle_conditions.get(status)
            if condition is not None:
                query = query.where(condition)
            elif status in {"uploaded", "queued", "processing", "completed", "failed"}:
                # Preserve the existing processing-status API contract for
                # callers that still need the raw backend state.
                query = query.where(Document.status == status)

        if search:
            search_pattern = f"%{search}%"
            query = query.join(Document.patient).where(
                or_(
                    Patient.first_name.ilike(search_pattern),
                    Patient.last_name.ilike(search_pattern),
                    Patient.mrn.ilike(search_pattern),
                    Document.document_type.ilike(search_pattern),
                    Document.file_name.ilike(search_pattern),
                )
            )

        # Count query
        count_query = select(func.count()).select_from(query.subquery())
        total_res = await self.session.execute(count_query)
        total = total_res.scalar() or 0

        # Paginated results
        offset = (page - 1) * page_size
        if sort == "name_asc":
            query = query.order_by(Document.file_name.asc(), Document.created_at.desc())
        elif sort == "status_asc":
            query = query.order_by(Document.status.asc(), Document.created_at.desc())
        else:
            query = query.order_by(Document.created_at.desc())
        query = query.offset(offset).limit(page_size)
        res = await self.session.execute(query)
        docs = res.scalars().all()

        items = []
        for d in docs:
            patient_name = (
            " ".join(
                part
                for part in [
                    d.patient.first_name if d.patient else None,
                    (
                        f"{d.patient.last_name[0]}."
                        if d.patient and d.patient.last_name
                        else None
                    ),
                ]
                if part
            )
            if d.patient and (d.patient.first_name or d.patient.last_name)
            else None
        )
            case_id = f"CL-{str(d.id)[:6].upper()}"

            # Deriving confidence
            avg_conf = None
            if d.extractions:
                all_entities = [e for ext in d.extractions for e in ext.entities]
                if all_entities:
                    avg_conf = sum(e.confidence for e in all_entities) / len(all_entities)

            conf_str = ("high" if avg_conf is not None and avg_conf >= settings.review_confidence_threshold else "medium" if avg_conf is not None and avg_conf >= 0.65 else "low" if avg_conf is not None else "not_available")

            file_name = d.file_name or (d.versions[0].file_name if d.versions else None)

            items.append({
                "id": str(d.id),
                "case_id": case_id,
                "file_name": file_name,
                "patient_name": patient_name,
                "mrn": d.patient.mrn if d.patient else None,
                "doc_type": d.document_type,
                "status": d.status,
                "review_status": d.review_status,
                "lifecycle_status": derive_lifecycle_status(d.status, d.review_status),
                "confidence": conf_str,
                "last_updated": d.updated_at.isoformat(),
            })

        return items, total

    async def get_document_details(self, document_id: uuid.UUID) -> dict | None:
        query = select(Document).options(
            selectinload(Document.patient),
            selectinload(Document.versions),
            selectinload(Document.processing_jobs).selectinload(ProcessingJob.steps),
            selectinload(Document.extractions).selectinload(Extraction.entities),
        ).where(Document.id == document_id)

        res = await self.session.execute(query)
        d = res.scalars().first()
        if not d:
            return None

        patient_name = (
            " ".join(
                part
                for part in [
                    d.patient.first_name if d.patient else None,
                    (
                        f"{d.patient.last_name[0]}."
                        if d.patient and d.patient.last_name
                        else None
                    ),
                ]
                if part
            )
            if d.patient and (d.patient.first_name or d.patient.last_name)
            else None
        )
        case_id = f"CL-{str(d.id)[:6].upper()}"

        latest_ver = d.versions[-1] if d.versions else None
        source_text = latest_ver.raw_text if latest_ver else "No source text available."

        # Pipeline stages mapping for UI left-panel progress
        latest_job = d.processing_jobs[-1] if d.processing_jobs else None
        stages = []
        default_stage_names = [
            "Uploaded", "Validated", "Preprocessed", "NLP Analysis",
            "LLM Extraction", "Validation Rules", "Medical Normalization", "Final Review", "Completed"
        ]

        if latest_job and latest_job.steps:
            for s in latest_job.steps:
                stages.append({
                    "name": s.step_name.replace("_", " ").title(),
                    "status": "done" if s.status == "completed" else s.status,
                    "detail": f"{s.processing_ms}ms" if s.processing_ms else (s.model_version or "—"),
                    "throughput": f"{s.processing_ms / 1000:.1f}s" if s.processing_ms else "—",
                })
        else:
            for name in default_stage_names:
                stages.append({
                    "name": name,
                    "status": "done" if d.status == "completed" else "pending",
                    "detail": "—",
                    "throughput": "—",
                })

        # Deriving confidence
        avg_conf = None
        if d.extractions:
            all_entities = [e for ext in d.extractions for e in ext.entities]
            if all_entities:
                avg_conf = sum(e.confidence for e in all_entities) / len(all_entities)

        conf_str = (
            "high"
            if avg_conf is not None and avg_conf >= settings.review_confidence_threshold
            else "medium"
            if avg_conf is not None and avg_conf >= 0.65
            else "low"
            if avg_conf is not None
            else "not_available"
        )

        return {
            "id": str(d.id),
            "case_id": case_id,
            "patient_name": patient_name,
            "mrn": d.patient.mrn if d.patient else None,
            "dob": d.patient.dob.strftime("%Y-%m-%d") if d.patient and d.patient.dob else None,
            "doc_type": d.document_type,
            "status": d.status,
            "review_status": d.review_status,
            "lifecycle_status": derive_lifecycle_status(d.status, d.review_status),
            "confidence": conf_str,
            "source_text": source_text,
            "version_number": latest_ver.version_number if latest_ver else 1,
            "page_count": latest_ver.page_count if latest_ver and latest_ver.page_count is not None else 0,
            "file_name": d.file_name or "document.txt",
            "mime_type": d.mime_type or "text/plain",
            "size_bytes": d.size_bytes or len(source_text.encode("utf-8")),
            "last_updated": d.updated_at.isoformat(),
            "pipeline_stages": stages,
        }

    async def get_document_entities(self, document_id: uuid.UUID) -> List[dict] | None:
        doc_res = await self.session.execute(
            select(Document)
            .options(
                selectinload(Document.extractions)
                .selectinload(Extraction.entities)
                .selectinload(ClinicalEntity.evidence_spans),
                selectinload(Document.extractions)
                .selectinload(Extraction.entities)
                .selectinload(ClinicalEntity.validation_results),
            )
            .where(Document.id == document_id)
        )
        doc = doc_res.scalars().first()
        if not doc:
            return None

        entities = []
        for ext in doc.extractions:
            for entity in ext.entities:
                spans = [
                    {
                        "id": str(s.id),
                        "entity_id": str(s.entity_id),
                        "start_offset": s.start_offset,
                        "end_offset": s.end_offset,
                        "exact_text": s.text,
                        "sentence_text": None,
                        "section_name": None,
                    }
                    for s in entity.evidence_spans
                ]
                entities.append({
                    "id": str(entity.id),
                    "extraction_id": str(entity.extraction_id),
                    "entity_type": entity.entity_type,
                    "raw_text": entity.raw_text,
                    "normalized_value": entity.normalized_value,
                    "confidence": float(entity.confidence),
                    "assertion": entity.assertion,
                    "section": entity.section,
                    "status": entity.status,
                    "details": entity.details,
                    "validation_rule_codes": [v.rule_code or v.validation_rule.upper() for v in entity.validation_results if v.status in {"fail", "warning"}],
                    "evidence_spans": spans,
                })
        return entities

    async def get_document_evidence(self, document_id: uuid.UUID) -> List[dict] | None:
        entities = await self.get_document_entities(document_id)
        if entities is None:
            return None

        evidence_spans = []
        for entity in entities:
            evidence_spans.extend(entity.get("evidence_spans", []))
        return evidence_spans
