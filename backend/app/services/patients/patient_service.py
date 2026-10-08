"""Patient Domain Service — Clinical Timeline Aggregator."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Patient, Document, Extraction, ClinicalEntity


class PatientService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_patient_timeline(
        self,
        patient_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        query = (
            select(Patient)
            .options(
                selectinload(Patient.encounters),
                selectinload(Patient.documents)
                .selectinload(Document.extractions)
                .selectinload(Extraction.entities)
                .selectinload(ClinicalEntity.evidence_spans),
                selectinload(Patient.documents).selectinload(Document.review_tasks),
            )
            .where(Patient.id == patient_id)
        )

        result = await self.session.execute(query)
        patient = result.scalars().first()

        if not patient:
            return None

        events: list[dict[str, Any]] = []

        for encounter in patient.encounters:
            event_date = (
                encounter.admit_time.isoformat()
                if encounter.admit_time
                else encounter.created_at.isoformat()
            )

            if encounter.discharge_time:
                detail = (
                    f"Discharged: "
                    f"{encounter.discharge_time.strftime('%Y-%m-%d')}"
                )
            elif encounter.admit_time:
                detail = "Active"
            else:
                detail = "Encounter date unavailable"

            events.append(
                {
                    "id": str(encounter.id),
                    "type": "encounter",
                    "title": (
                        f"Encounter "
                        f"{encounter.external_encounter_id}"
                        if encounter.external_encounter_id
                        else "Clinical Encounter"
                    ),
                    "date": event_date,
                    "status": (
                        "discharged"
                        if encounter.discharge_time
                        else "active"
                    ),
                    "detail": detail,
                    "external_encounter_id": encounter.external_encounter_id,
                    "los_hours": (
                        float(encounter.los_hours)
                        if encounter.los_hours is not None
                        else None
                    ),
                }
            )

        for document in patient.documents:
            entities_summary: list[str] = []

            for extraction in document.extractions:
                for entity in extraction.entities:
                    value = entity.normalized_value or entity.raw_text
                    entities_summary.append(
                        f"{entity.entity_type.title()}: {value}"
                    )

            events.append(
                {
                    "id": str(document.id),
                    "type": "document",
                    "title": f"Document: {document.document_type}",
                    "date": document.created_at.isoformat(),
                    "status": document.status,
                    "detail": f"{len(entities_summary)} entities extracted",
                    "entities": entities_summary[:5],
                }
            )

        events.sort(key=lambda event: event["date"], reverse=True)

        full_name = None
        if patient.first_name or patient.last_name:
            full_name = " ".join(
                part
                for part in [patient.first_name, patient.last_name]
                if part
            )

        return {
            "patient_id": str(patient.id),
            "external_patient_id": patient.external_patient_id,
            "mrn": patient.mrn,
            "full_name": full_name,
            "gender": patient.gender,
            "dob": (
                patient.dob.strftime("%Y-%m-%d")
                if patient.dob
                else None
            ),
            "timeline_events": events,
        }
