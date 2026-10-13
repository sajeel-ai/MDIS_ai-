"""Extraction schema, evidence, assertion, and section regression coverage."""

import pytest

from app.providers.extraction.local import LocalExtractionProvider
from app.providers.extraction.mock import MockExtractionProvider
from app.providers.extraction.context import detect_assertion, detect_section
from app.schemas.entity_contract import ExtractedEntity, validate_entity_candidates, verify_or_relocate_evidence


def test_required_assertion_examples():
    provider = LocalExtractionProvider()
    cases = [
        ("no diabetes", "Diabetes mellitus", "absent"),
        ("rule out pneumonia", "Pneumonia", "possible"),
        ("history of hypertension", "Hypertension", "historical"),
        ("mother has diabetes", "Diabetes mellitus", "family"),
    ]
    import asyncio

    for text, normalized, assertion in cases:
        result = asyncio.run(provider.extract_clinical_entities(text))
        found = next(entity for entity in result["entities"] if entity["normalized_value"] == normalized)
        assert found["assertion"] == assertion

    result = asyncio.run(provider.extract_clinical_entities("denies chest pain but reports cough"))
    assertions = {entity["normalized_value"]: entity["assertion"] for entity in result["entities"]}
    assert assertions["Chest pain"] == "absent"
    assert assertions["Cough"] == "present"


@pytest.mark.parametrize(
    ("text", "term", "expected"),
    [
        ("The patient reports no history of asthma.", "Asthma", "absent"),
        ("There is no known chronic obstructive pulmonary disease.", "Chronic obstructive pulmonary disease", "absent"),
        ("Negative for chest pain, dyspnea, or fever.", "Fever", "absent"),
        ("Denies abdominal pain but reports knee pain.", "Abdominal pain", "absent"),
        ("Denies abdominal pain but reports knee pain.", "Knee pain", "present"),
        ("Ibuprofen was discontinued.", "Ibuprofen", "discontinued"),
        ("Rosuvastatin 20 mg every night.", "Rosuvastatin", "present"),
    ],
)
def test_assertion_context_handles_negation_history_and_discontinuation(text, term, expected):
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    found = next((entity for entity in entities if entity["normalized_value"] == term), None)
    assert found is not None
    assert found["assertion"] == expected


def test_no_known_drug_allergies_does_not_create_allergy_context():
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities("No known drug allergies."))["entities"]
    assert not any(entity["type"] == "medication" and entity["section"] == "ALLERGIES" for entity in entities)


def test_vital_signs_are_structured_without_treating_doses_as_vitals():
    import asyncio

    text = "Arrival vitals: BP 124/78 mmHg, HR 72 bpm, RR 16, T 37.2 C, SpO2 97% RA. Take 500 mg medication."
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    vitals = [entity for entity in entities if entity["type"] == "vital"]
    assert {entity["normalized_value"] for entity in vitals} == {"Blood pressure", "Heart rate", "Respiratory rate", "Body temperature", "Oxygen saturation"}
    bp = next(entity for entity in vitals if entity["normalized_value"] == "Blood pressure")
    assert bp["details"]["systolic"] == 124 and bp["details"]["diastolic"] == 78
    assert text[bp["start_offset"]:bp["end_offset"]] == bp["evidence_text"]
    assert not any(entity["type"] == "vital" and "500" in entity["raw_text"] for entity in entities)


def test_each_vital_reading_is_kept_separate_and_implausible_values_flagged():
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities("BP 150/90 mmHg; discharge BP 118/76 mmHg; BP 40/200 mmHg"))["entities"]
    readings = [entity for entity in entities if entity["type"] == "vital" and entity["normalized_value"] == "Blood pressure"]
    assert len(readings) == 3
    assert "implausible_blood_pressure" in readings[-1]["details"]["validation_warnings"]


def test_vitals_table_rows_are_parsed_without_capture_group_assumptions():
    import asyncio

    text = "Vital | Value | Unit\nTemperature | 37.2 | C\nHeart Rate | 72 | bpm\nSpO2 | 98 | %"
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    assert {entity["normalized_value"] for entity in entities} >= {"Body temperature", "Heart rate", "Oxygen saturation"}


def test_two_column_blood_pressure_table_is_parsed():
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities("Blood Pressure | 120 | 80"))["entities"]
    bp = next(entity for entity in entities if entity["normalized_value"] == "Blood pressure")
    assert bp["details"]["systolic"] == 120
    assert bp["details"]["diastolic"] == 80


def test_vitals_table_missing_unit_is_kept_and_flagged():
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities("Temperature | 37.2"))["entities"]
    temperature = next(entity for entity in entities if entity["normalized_value"] == "Body temperature")
    assert "missing_vital_unit" in temperature["details"]["validation_warnings"]


def test_mixed_table_and_sentence_vitals_are_both_retained():
    import asyncio

    text = "Heart Rate | 72 | bpm\nBP 128/80 mmHg; SpO2 97% RA"
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    assert sum(entity["normalized_value"] == "Heart rate" for entity in entities) == 1
    assert sum(entity["normalized_value"] == "Blood pressure" for entity in entities) == 1
    assert sum(entity["normalized_value"] == "Oxygen saturation" for entity in entities) == 1


def test_malformed_vital_input_returns_empty_or_flagged_result():
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities("Blood Pressure | not available"))["entities"]
    assert all(entity.get("details", {}).get("validation_warnings") or entity["type"] != "vital" for entity in entities)


def test_advice_and_conditional_mentions_are_not_findings():
    import asyncio

    text = "Return if chest pain develops; seek care if fever occurs."
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    assert entities == []


@pytest.mark.parametrize(
    ("text", "normalized"),
    [("COPD is documented.", "Chronic obstructive pulmonary disease"), ("HTN is documented.", "Hypertension")],
)
def test_hybrid_terminology_abbreviation_expansions_are_deterministic(text, normalized):
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    assert any(entity["normalized_value"] == normalized for entity in entities)


def test_vitals_are_not_labs():
    import asyncio

    text = "BP 124/78 mmHg; HR 72; RR 16; T 37.2 C; SpO2 97% RA; weight 70 kg; height 175 cm; BMI 22.9"
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    assert any(entity["type"] == "vital" for entity in entities)
    assert not any(entity["type"] == "lab" for entity in entities)


def test_same_concept_merges_evidence_but_assertion_conflicts_remain_separate():
    import asyncio

    merged = asyncio.run(LocalExtractionProvider().extract_clinical_entities("Cough is present. The patient reports cough again."))["entities"]
    coughs = [entity for entity in merged if entity["normalized_value"] == "Cough"]
    assert len(coughs) == 1
    assert len(coughs[0]["details"]["evidence_spans"]) == 2

    conflict = asyncio.run(LocalExtractionProvider().extract_clinical_entities("Cough is present. No cough today."))["entities"]
    coughs = [entity for entity in conflict if entity["normalized_value"] == "Cough"]
    assert {entity["assertion"] for entity in coughs} == {"present", "absent"}
    assert all(entity["details"]["assertion_conflict"] for entity in coughs)


def test_pain_modifiers_and_coordinated_negation_are_preserved():
    import asyncio

    text = "Mild right knee pain; lower back pain; right upper quadrant pain; pain in the left knee; denies chest and abdominal pain; no pain in the throat."
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    pains = [entity for entity in entities if entity["type"] == "symptom" and "pain" in entity["normalized_value"].lower()]
    assert any(entity["details"].get("severity") == "mild" and entity["details"].get("laterality") == "right" for entity in pains)
    assert any(entity["details"].get("site") == "lower back" for entity in pains)
    assert any(entity["details"].get("site") == "upper quadrant" for entity in pains)
    assert any(entity["details"].get("laterality") == "left" and entity["details"].get("site") == "knee" for entity in pains)
    assert sum(entity["assertion"] == "absent" for entity in pains) == 3


def test_incomplete_lab_rows_are_retained_for_validation():
    import asyncio

    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities("Hemoglobin: 10.2"))["entities"]
    lab = next(entity for entity in entities if entity["type"] == "lab")
    assert lab["details"]["value"] == "10.2"
    assert "incomplete_lab_row" in lab["details"]["validation_warnings"]


def test_medication_instructions_do_not_bleed_between_lines_and_bedtime_is_preserved():
    import asyncio

    text = "Medicines: Drug A 10 mg twice daily\nDrug B 20 mg at bedtime\nDrug C 5 mg stopped."
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    meds = {entity["normalized_value"]: entity for entity in entities if entity["type"] == "medication"}
    # Unsupported names are intentionally ignored; use supported medicines in a
    # generalized list to verify line-local dose/frequency capture.
    text = "Metformin 500 mg twice daily\nAtorvastatin 20 mg at bedtime\nAspirin discontinued."
    meds = {
        entity["normalized_value"]: entity
        for entity in asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
        if entity["type"] == "medication"
    }
    assert meds["Metformin"]["details"] == {"dose": "500 mg", "frequency": "twice daily"}
    assert meds["Atorvastatin"]["details"] == {"dose": "20 mg", "frequency": "at bedtime"}
    assert meds["Aspirin"]["details"] == {}


@pytest.mark.parametrize("instruction", ["at bedtime", "qHS", "nightly", "every night"])
def test_nighttime_medication_instructions_are_preserved(instruction):
    import asyncio

    text = f"Rosuvastatin 10 mg {instruction}."
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    medication = next(entity for entity in entities if entity["type"] == "medication")
    assert medication["details"]["frequency"].casefold() == instruction.casefold()


def test_location_pain_uses_negation_scope_and_preserves_positive_exception():
    import asyncio

    text = "The patient denies back pain but reports right knee pain."
    entities = asyncio.run(LocalExtractionProvider().extract_clinical_entities(text))["entities"]
    pains = {entity["normalized_value"]: entity for entity in entities if entity["type"] == "symptom"}
    assert pains["Back pain"]["assertion"] == "absent"
    assert pains["Knee pain"]["assertion"] == "present"


def test_local_and_mock_provider_outputs_meet_the_entity_contract():
    import asyncio

    for provider in (LocalExtractionProvider(), MockExtractionProvider()):
        result = asyncio.run(provider.extract_clinical_entities("pneumonia with cough and amoxicillin"))
        accepted, rejected = validate_entity_candidates(result["entities"])
        assert accepted
        assert rejected == []


def test_section_detection_and_allergy_medication_section():
    text = "ALLERGIES\nAmoxicillin"
    section = detect_section(text, text.index("Amoxicillin"))
    assert section == "ALLERGIES"
    assert detect_assertion(text, text.index("Amoxicillin"), len(text), section).value == "present"
    inline = "ALLERGIES: Amoxicillin"
    assert detect_section(inline, inline.index("Amoxicillin")) == "ALLERGIES"


def test_invalid_provider_entities_are_rejected_without_source_values():
    accepted, rejected = validate_entity_candidates([
        {"type": "diagnosis", "raw_text": "private source phrase", "confidence": 0.4}
    ])
    assert accepted == []
    assert rejected == [{"index": 0, "reason": "invalid_fields:assertion,code,code_system,end_offset,evidence_text,normalized_value,page_number,section,start_offset"}]
    assert "private source phrase" not in str(rejected)


def test_evidence_is_relocated_by_exact_search_or_marked_unverified():
    entity = ExtractedEntity.model_validate({
        "type": "diagnosis", "raw_text": "pneumonia", "normalized_value": "Pneumonia",
        "code": "J18.9", "code_system": "ICD10", "confidence": 0.7,
        "assertion": "present", "section": None, "start_offset": 0, "end_offset": 9,
        "evidence_text": "pneumonia", "page_number": 1,
    })
    relocated, verified = verify_or_relocate_evidence("No evidence of pneumonia", entity)
    assert verified is True
    assert relocated.start_offset == 15
    missing, verified = verify_or_relocate_evidence("No evidence of diabetes", entity)
    assert verified is False
    assert missing.start_offset == 0


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01])
def test_entity_confidence_must_be_between_zero_and_one(bad_confidence):
    with pytest.raises(ValueError):
        ExtractedEntity.model_validate({
            "type": "diagnosis", "raw_text": "x", "normalized_value": "X",
            "code": None, "code_system": None, "confidence": bad_confidence,
            "assertion": "present", "section": None, "start_offset": 0,
            "end_offset": 1, "evidence_text": "x", "page_number": 1,
        })
