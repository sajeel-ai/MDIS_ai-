"""FHIR document projection and base-resource model validation."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ClinicalEntity, Document, Extraction, ReviewTask

FHIR_NAMESPACE = uuid.UUID("136e5e39-b26c-5d88-9c63-986d33da8c35")
FHIR_SYSTEMS = {
    "icd-10": "http://hl7.org/fhir/sid/icd-10",
    "icd10": "http://hl7.org/fhir/sid/icd-10",
    "snomed": "http://snomed.info/sct",
    "snomed ct": "http://snomed.info/sct",
    "rxnorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "loinc": "http://loinc.org",
    "cpt": "http://www.ama-assn.org/go/cpt",
}
DOCUMENT_TYPE_CODES = {
    "discharge_summary": ("18842-5", "http://loinc.org"),
    "progress_note": ("11506-3", "http://loinc.org"),
}


def _id(resource_key: str) -> str:
    return str(uuid.uuid5(FHIR_NAMESPACE, resource_key))


def _entry(resource: dict[str, Any], key: str) -> dict[str, Any]:
    resource.setdefault("id", _id(key))
    return {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource}


def _concept(value: str | None, details: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    code = details.get("code")
    raw_system = str(details.get("code_system") or "").strip().lower()
    system = FHIR_SYSTEMS.get(raw_system)
    if code and system and details.get("code_verified") is True:
        result["coding"] = [{"system": system, "code": str(code), "display": value or str(code)}]
    if value and not result.get("coding"):
        result["text"] = value
    return result or {"text": value or "Uncoded"}


def normalize_gender(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"m", "male"}:
        return "male"
    if normalized in {"f", "female"}:
        return "female"
    if normalized == "other":
        return "other"
    return "unknown"


def _date(value: datetime | None) -> str:
    if value is None:
        raise ValueError("FHIR document export requires a recorded document date")
    return value.isoformat()


def build_document_fhir_bundle(document: Document, *, include_unreviewed: bool = False) -> dict[str, Any]:
    """Build a self-contained document bundle from already-loaded ORM objects."""
    patient = document.patient
    if patient is None:
        raise ValueError("FHIR document export requires a linked patient")

    doc_id = str(document.id)
    patient_id = str(patient.id)
    timestamp = _date(document.created_at)
    patient_resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "gender": normalize_gender(patient.gender),
    }
    if patient.mrn:
        patient_resource["identifier"] = [{"system": "urn:cognate:mrn", "value": patient.mrn}]
    if patient.first_name or patient.last_name:
        name: dict[str, Any] = {}
        if patient.first_name:
            name["given"] = [patient.first_name]
        if patient.last_name:
            name["family"] = patient.last_name
        patient_resource["name"] = [name]
    if patient.dob:
        patient_resource["birthDate"] = patient.dob.isoformat()

    device_id = _id(f"{doc_id}:author-device")
    device = {"resourceType": "Device", "id": device_id, "status": "active", "deviceName": [{"name": "Cognate document exporter", "type": "model-name"}]}
    docref_id = _id(f"{doc_id}:document-reference")
    document_reference = {
        "resourceType": "DocumentReference",
        "id": docref_id,
        "status": "current",
        "subject": {"reference": f"Patient/{patient_id}"},
        "date": timestamp,
        "content": [{"attachment": {"contentType": document.mime_type or "application/octet-stream", "title": document.file_name or document.document_type}}],
    }

    included: list[dict[str, Any]] = []
    section_refs: list[dict[str, str]] = []
    source_refs: dict[str, str] = {}
    reviewers: dict[str, str] = {}
    entities: list[ClinicalEntity] = []
    for extraction in document.extractions or []:
        entities.extend(extraction.entities or [])

    for entity in entities:
        approved = entity.status == "approved"
        if entity.assertion != "present":
            continue
        if not approved and not include_unreviewed:
            continue
        if entity.status not in {"approved", "unreviewed"}:
            continue

        details = entity.details or {}
        value = entity.normalized_value or entity.raw_text
        allergy = entity.entity_type == "medication" and (entity.section or "").strip().lower() in {"allergies", "allergy"}
        if entity.entity_type == "diagnosis":
            resource: dict[str, Any] = {
                "resourceType": "Condition", "subject": {"reference": f"Patient/{patient_id}"},
                "code": _concept(value, details),
                "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
                "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed" if approved else "unconfirmed"}]},
            }
        elif allergy:
            resource = {
                "resourceType": "AllergyIntolerance", "patient": {"reference": f"Patient/{patient_id}"},
                "code": _concept(value, details), "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
            }
        elif entity.entity_type == "medication":
            medication = _concept(value, details)
            if details.get("explicit_prescription") is True:
                resource = {"resourceType": "MedicationRequest", "status": "active", "intent": "order", "subject": {"reference": f"Patient/{patient_id}"}, "medicationCodeableConcept": medication}
            else:
                resource = {"resourceType": "MedicationStatement", "status": "active", "subject": {"reference": f"Patient/{patient_id}"}, "medicationCodeableConcept": medication}
        elif entity.entity_type in {"lab", "lab_result", "observation"}:
            resource = {"resourceType": "Observation", "status": "final", "subject": {"reference": f"Patient/{patient_id}"}, "code": _concept(value, details)}
            lab_value = details.get("value")
            unit = details.get("unit")
            try:
                numeric_value = float(lab_value) if lab_value is not None else None
            except (TypeError, ValueError):
                numeric_value = None
            if numeric_value is not None and unit:
                resource["valueQuantity"] = {"value": numeric_value, "unit": str(unit), "system": "http://unitsofmeasure.org", "code": str(details.get("unit_code") or unit)}
            reference_range = details.get("reference_range")
            if isinstance(reference_range, dict):
                resource["referenceRange"] = [reference_range]
        elif entity.entity_type == "procedure":
            resource = {"resourceType": "Procedure", "status": details.get("status") if details.get("status") in {"preparation", "in-progress", "not-done", "on-hold", "stopped", "completed", "entered-in-error", "unknown"} else "unknown", "subject": {"reference": f"Patient/{patient_id}"}, "code": _concept(value, details)}
        else:
            continue

        resource_id = str(entity.id)
        resource["id"] = resource_id
        if not approved:
            resource["extension"] = [{"url": "urn:cognate:export-status", "valueCode": "unconfirmed"}]
        entity_entry = _entry(resource, f"{doc_id}:entity:{resource_id}")
        included.append(entity_entry)
        source_refs[resource_id] = f"{resource['resourceType']}/{resource_id}"
        section_refs.append({"reference": source_refs[resource_id]})

        reviewer_id = next((str(task.assigned_to) for task in (entity.review_tasks or []) if task.status == "approved" and task.assigned_to), None)
        if approved and reviewer_id:
            reviewers[reviewer_id] = reviewer_id

    reviewer_entries = [_entry({"resourceType": "Practitioner", "id": user_id}, f"{doc_id}:reviewer:{user_id}") for user_id in reviewers]
    reviewer_refs = {entry["resource"]["id"]: f"Practitioner/{entry['resource']['id']}" for entry in reviewer_entries}
    provenance_entries: list[dict[str, Any]] = []
    for resource_id, target in source_refs.items():
        entity = next((candidate for candidate in entities if str(candidate.id) == resource_id), None)
        if not entity:
            continue
        reviewer_id = next((str(task.assigned_to) for task in (entity.review_tasks or []) if task.status == "approved" and task.assigned_to), None)
        agent_ref = reviewer_refs.get(reviewer_id) if reviewer_id else f"Device/{device_id}"
        provenance_id = _id(f"{doc_id}:provenance:{resource_id}")
        provenance_entries.append(_entry({
            "resourceType": "Provenance", "id": provenance_id, "recorded": timestamp,
            "target": [{"reference": target}],
            "entity": [{"role": "source", "what": {"reference": f"DocumentReference/{docref_id}"}}],
            "agent": [{"type": {"text": "reviewer approval" if reviewer_id else "document projection"}, "who": {"reference": agent_ref}}],
        }, f"{doc_id}:provenance:{resource_id}"))

    composition_id = _id(f"{doc_id}:composition")
    doc_type = str(document.document_type or "Clinical document")
    type_code = DOCUMENT_TYPE_CODES.get(doc_type.lower())
    composition_type = {"coding": [{"system": type_code[1], "code": type_code[0]}]} if type_code else {"text": doc_type}
    composition = {
        "resourceType": "Composition", "id": composition_id, "status": "final", "type": composition_type,
        "identifier": {"system": "urn:cognate:document", "value": doc_id},
        "subject": {"reference": f"Patient/{patient_id}"}, "date": timestamp,
        "author": [{"reference": f"Device/{device_id}"}], "title": doc_type,
        "section": [{"title": "Clinical resources", "entry": section_refs}] if section_refs else [],
    }
    entries = [
        _entry(composition, f"{doc_id}:composition"),
        _entry(patient_resource, f"{doc_id}:patient"),
        _entry(device, f"{doc_id}:author-device"),
        _entry(document_reference, f"{doc_id}:document-reference"),
        *reviewer_entries,
        *included,
        *provenance_entries,
    ]
    bundle = {"resourceType": "Bundle", "type": "document", "timestamp": timestamp, "entry": entries}
    validate_bundle_model(bundle)
    return bundle


def validate_bundle_model(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate with available FHIR resource models and document-bundle invariants."""
    from fhir.resources.R4B.bundle import Bundle

    parsed = Bundle.parse_obj(bundle).dict(exclude_none=True)
    bundle_types = {"document", "message", "transaction", "transaction-response", "batch", "batch-response", "history", "searchset", "collection"}
    if parsed.get("type") not in bundle_types:
        raise ValueError("FHIR Bundle.type is not a valid R4 value")
    entries = parsed.get("entry") or []
    if parsed.get("type") == "document" and (not entries or entries[0].get("resource", {}).get("resourceType") != "Composition"):
        raise ValueError("FHIR document Bundle must begin with Composition")
    full_urls: set[str] = set()
    resource_refs: set[str] = set()
    for entry in entries:
        full_url = entry.get("fullUrl", "")
        resource = entry.get("resource", {})
        if not full_url.startswith("urn:uuid:"):
            raise ValueError("Every FHIR bundle entry must use a urn:uuid fullUrl")
        try:
            uuid.UUID(full_url.removeprefix("urn:uuid:"))
        except ValueError as exc:
            raise ValueError("FHIR bundle fullUrl must contain a UUID") from exc
        if full_url in full_urls:
            raise ValueError("FHIR bundle fullUrl values must be unique")
        full_urls.add(full_url)
        resource_refs.add(f"{resource.get('resourceType')}/{resource.get('id')}")

    def references(value: Any):
        if isinstance(value, dict):
            reference = value.get("reference")
            if isinstance(reference, str):
                yield reference
            for child in value.values():
                yield from references(child)
        elif isinstance(value, list):
            for child in value:
                yield from references(child)

    unresolved = [ref for ref in references(parsed) if ref not in resource_refs]
    if unresolved:
        raise ValueError("FHIR bundle contains an unresolved internal reference")
    if parsed.get("type") == "document":
        composition = entries[0]["resource"]
        required = ("identifier", "status", "type", "subject", "date", "author", "title")
        if any(not composition.get(key) for key in required):
            raise ValueError("FHIR Composition is missing a required document field")
    return parsed


class FHIRProjectionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_document_fhir_bundle(self, document_id: uuid.UUID, *, include_unreviewed: bool = False) -> dict[str, Any] | None:
        query = select(Document).options(
            selectinload(Document.patient),
            selectinload(Document.extractions).selectinload(Extraction.entities).selectinload(ClinicalEntity.evidence_spans),
            selectinload(Document.extractions).selectinload(Extraction.entities).selectinload(ClinicalEntity.review_tasks),
        ).where(Document.id == document_id)
        result = await self.session.execute(query)
        document = result.scalars().first()
        if document is None:
            return None
        return build_document_fhir_bundle(document, include_unreviewed=include_unreviewed)
