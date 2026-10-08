"""Multi-Format Document Exporter Service (JSON, CSV, FHIR)."""

import csv
import io
import json
import uuid
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Document, Extraction, ClinicalEntity

from app.services.fhir.fhir_service import FHIRProjectionService


class ExporterService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def export_document(self, document_id: uuid.UUID, export_format: str, *, include_unreviewed: bool = False) -> Tuple[str, str, str]:
        fmt = export_format.lower()
        if fmt == "fhir":
            fhir_service = FHIRProjectionService(self.session)
            bundle = await fhir_service.generate_document_fhir_bundle(document_id, include_unreviewed=include_unreviewed)
            if bundle is None:
                raise ValueError(f"Document {document_id} not found")
            content = json.dumps(bundle, indent=2)
            return content, "application/json", f"document_{str(document_id)[:8]}.fhir.json"

        query = select(Document).options(
            selectinload(Document.patient),
            selectinload(Document.extractions).selectinload(Extraction.entities).selectinload(ClinicalEntity.evidence_spans)
        ).where(Document.id == document_id)


        res = await self.session.execute(query)
        doc = res.scalars().first()
        if not doc:
            raise ValueError(f"Document {document_id} not found")

        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Document_ID", "Patient_MRN", "Entity_Type", "Raw_Text", "Normalized_Value", "Code", "Model_Confidence_Uncalibrated", "Assertion", "Section", "Active_Fact"])

            mrn = doc.patient.mrn if doc.patient else None
            if doc.extractions:
                for ext in doc.extractions:
                    for ent in ext.entities:
                        active_fact = ent.assertion == "present" and not (
                            ent.entity_type == "medication" and ent.section == "ALLERGIES"
                        )
                        writer.writerow([str(doc.id), mrn, ent.entity_type, ent.raw_text, ent.normalized_value, (ent.details or {}).get("code"), ent.confidence, ent.assertion, ent.section, active_fact])

            return output.getvalue(), "text/csv", f"document_{str(document_id)[:8]}.csv"

        # Default JSON export
        export_data = {
            "document_id": str(doc.id),
            "document_type": doc.document_type,
            "patient_mrn": doc.patient.mrn if doc.patient else None,
            "status": doc.status,
            "review_status": doc.review_status,
            "extractions": [],
        }

        if doc.extractions:
            for ext in doc.extractions:
                for ent in ext.entities:
                    ev_span = ent.evidence_spans[0].exact_text if ent.evidence_spans else ""
                    export_data["extractions"].append({
                        "entity_type": ent.entity_type,
                        "raw_text": ent.raw_text,
                        "normalized_value": ent.normalized_value,
                        "code": (ent.details or {}).get("code"),
                        "confidence": ent.confidence,
                        "assertion": ent.assertion,
                        "section": ent.section,
                        "active_fact": ent.assertion == "present" and not (
                            ent.entity_type == "medication" and ent.section == "ALLERGIES"
                        ),
                        "evidence": ev_span,
                    })

        return json.dumps(export_data, indent=2), "application/json", f"document_{str(document_id)[:8]}.json"
