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
