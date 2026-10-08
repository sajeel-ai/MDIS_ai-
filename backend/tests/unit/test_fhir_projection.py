"""FHIR export contract tests using only synthetic, de-identified data."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.fhir.fhir_service import build_document_fhir_bundle, normalize_gender, validate_bundle_model


def make_document(*entities, gender="unknown", index="test"):
    patient_id = uuid.uuid5(uuid.NAMESPACE_URL, f"patient-{index}")
    patient = SimpleNamespace(id=patient_id, gender=gender, mrn=None, first_name=None, last_name=None, dob=None)
    document_id = uuid.uuid5(uuid.NAMESPACE_URL, f"document-{index}")
    return SimpleNamespace(
        id=document_id, patient=patient, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc), document_type="progress_note",
        mime_type="application/pdf", file_name="synthetic.pdf",
        extractions=[SimpleNamespace(entities=list(entities))],
    )


def make_entity(entity_type, *, status="approved", assertion="present", section="CLINICAL", details=None, index="entity", reviewer=None):
    task = SimpleNamespace(status="approved", assigned_to=reviewer) if reviewer else None
    return SimpleNamespace(
        id=uuid.uuid5(uuid.NAMESPACE_URL, index), entity_type=entity_type, status=status,
        assertion=assertion, section=section, details=details or {}, normalized_value="Synthetic item",
        raw_text="Synthetic item", review_tasks=[task] if task else [],
    )


def resources(bundle):
    return [entry["resource"] for entry in bundle["entry"]]


def test_document_bundle_starts_with_composition_and_references_resolve():
    reviewer_id = uuid.uuid5(uuid.NAMESPACE_URL, "reviewer")
    entity = make_entity("diagnosis", reviewer=reviewer_id)
    bundle = build_document_fhir_bundle(make_document(entity))
    assert bundle["type"] == "document"
    assert bundle["entry"][0]["resource"]["resourceType"] == "Composition"
    assert all(entry["fullUrl"].startswith("urn:uuid:") for entry in bundle["entry"])
    resources_by_reference = {f"{r['resourceType']}/{r['id']}" for r in resources(bundle)}
    assert len(resources_by_reference) == len(bundle["entry"])

    def references(value):
        if isinstance(value, dict):
            if isinstance(value.get("reference"), str):
                yield value["reference"]
            for child in value.values():
                yield from references(child)
        elif isinstance(value, list):
            for child in value:
                yield from references(child)

    assert all(ref in resources_by_reference for ref in references(bundle))
    provenance = next(resource for resource in resources(bundle) if resource["resourceType"] == "Provenance")
    assert provenance["agent"][0]["who"]["reference"] == f"Practitioner/{reviewer_id}"
    assert provenance["entity"][0]["what"]["reference"].startswith("DocumentReference/")


@pytest.mark.parametrize(("raw", "expected"), [
    ("M", "male"), ("male", "male"), ("F", "female"), ("female", "female"),
    ("other", "other"), ("Unknown", "unknown"), (None, "unknown"), ("unmapped", "unknown"),
])
def test_patient_gender_never_defaults_to_male(raw, expected):
    assert normalize_gender(raw) == expected
    patient = next(resource for resource in resources(build_document_fhir_bundle(make_document(gender=raw))) if resource["resourceType"] == "Patient")
    assert patient["gender"] == expected


def test_only_approved_present_entities_export_unless_include_unreviewed_is_requested():
    approved = make_entity("diagnosis", index="approved")
    unreviewed = make_entity("procedure", status="unreviewed", index="unreviewed")
    absent = make_entity("medication", assertion="absent", index="absent")
    rejected = make_entity("diagnosis", status="rejected", index="rejected")
    document = make_document(approved, unreviewed, absent, rejected)
    normal = resources(build_document_fhir_bundle(document))
    assert [r["resourceType"] for r in normal].count("Condition") == 1
    assert "Procedure" not in [r["resourceType"] for r in normal]
    included = resources(build_document_fhir_bundle(document, include_unreviewed=True))
    procedure = next(r for r in included if r["resourceType"] == "Procedure")
    assert procedure["extension"][0]["valueCode"] == "unconfirmed"


def test_labs_allergies_medication_statements_and_verified_coding_map_correctly():
    lab = make_entity("lab_result", details={"value": "7.2", "unit": "mmol/L", "reference_range": {"text": "Synthetic range"}}, index="lab")
    allergy = make_entity("medication", section="ALLERGIES", index="allergy")
    medication = make_entity("medication", index="medication")
    prescription = make_entity("medication", details={"explicit_prescription": True}, index="prescription")
    diagnosis = make_entity("diagnosis", details={"code": "E11", "code_system": "ICD-10", "code_verified": True}, index="code")
    bundle = build_document_fhir_bundle(make_document(lab, allergy, medication, prescription, diagnosis))
    exported = resources(bundle)
    observation = next(r for r in exported if r["resourceType"] == "Observation")
    assert observation["valueQuantity"]["value"] == 7.2
    assert observation["valueQuantity"]["unit"] == "mmol/L"
    assert observation["referenceRange"][0]["text"] == "Synthetic range"
    assert any(r["resourceType"] == "AllergyIntolerance" for r in exported)
    assert any(r["resourceType"] == "MedicationStatement" for r in exported)
    assert any(r["resourceType"] == "MedicationRequest" for r in exported)
    condition = next(r for r in exported if r["resourceType"] == "Condition")
    assert condition["code"]["coding"][0]["system"] == "http://hl7.org/fhir/sid/icd-10"
    uncoded_condition = make_entity("diagnosis", details={"code": "unknown", "code_system": "unknown"}, index="uncoded")
    codeable = next(r for r in resources(build_document_fhir_bundle(make_document(uncoded_condition, index="uncoded-doc"))) if r["resourceType"] == "Condition")["code"]
    assert "coding" not in codeable


def test_ten_synthetic_document_bundles_validate_with_available_fhir_models():
    kinds = ["diagnosis", "medication", "lab_result", "procedure", "medication"]
    for index in range(10):
        kind = kinds[index % len(kinds)]
        section = "ALLERGIES" if index % 5 == 4 else "CLINICAL"
        detail = {"value": "7.2", "unit": "mmol/L"} if kind == "lab_result" else {}
        bundle = build_document_fhir_bundle(make_document(make_entity(kind, section=section, details=detail, index=f"synthetic-{index}"), index=f"synthetic-{index}"))
        assert validate_bundle_model(bundle)["type"] == "document"


def test_invalid_bundle_is_rejected_by_resource_validator():
    with pytest.raises(ValueError):
        validate_bundle_model({"resourceType": "Bundle", "type": "not-a-fhir-bundle-type"})
