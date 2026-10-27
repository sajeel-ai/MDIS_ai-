from app.providers.extraction.context import detect_assertion, detect_experiencer, detect_section, detect_temporality
from app.schemas.entity_contract import Assertion, EntityType, ExtractedEntity, verify_or_relocate_evidence
from app.services.extraction.review_contract import (
    build_ocr_page_metadata,
    derive_entity_group,
    evidence_bbox_and_confidence,
    locate_evidence,
    derive_exclusion_reason,
)


def _span(text: str, value: str):
    start = text.index(value)
    section = detect_section(text, start)
    assertion = detect_assertion(text, start, start + len(value), section)
    return section, assertion


SECTION_CASES = [
    ("Chief Complaint:\nCough", "Cough", "CHIEF COMPLAINT"),
    ("CC: Cough", "Cough", "CHIEF COMPLAINT"),
    ("HPI:\nCough", "Cough", "HISTORY OF PRESENT ILLNESS"),
    ("PMH: asthma", "asthma", "PAST MEDICAL HISTORY"),
    ("Past Surgical History:\nappendectomy", "appendectomy", "SURGICAL HISTORY"),
    ("Medications: aspirin", "aspirin", "MEDICATIONS"),
    ("Allergy: penicillin", "penicillin", "ALLERGIES"),
    ("Family Medical History: mother had MI", "MI", "FAMILY HISTORY"),
    ("Social History: former smoker", "smoker", "SOCIAL HISTORY"),
    ("ROS: denies cough", "cough", "REVIEW OF SYSTEMS"),
    ("Physical Exam: clear lungs", "lungs", "EXAM"),
    ("Lab Results: sodium 140", "sodium", "LABS"),
    ("Assessment: asthma", "asthma", "ASSESSMENT"),
    ("Treatment Plan: start therapy", "therapy", "PLAN"),
    ("Discharge Instructions: call if worse", "worse", "DISCHARGE INSTRUCTIONS"),
]


def test_section_header_variants_and_unknown_fallback():
    for note, term, expected in SECTION_CASES:
        assert detect_section(note, note.index(term)) == expected
    assert detect_section("Cough without a heading", 0) == "unknown"


ASSERTION_CASES = [
    ("Denies fever or chills", "fever", "absent"),
    ("Chest pain: negative", "Chest pain", "absent"),
    ("No history of MI", "MI", "absent"),
    ("No evidence of pneumonia", "pneumonia", "absent"),
    ("Mother had breast cancer", "breast cancer", "family"),
    ("Husband has diabetes", "diabetes", "present"),
    ("History of pneumonia in 2015", "pneumonia", "historical"),
    ("Rule out PE", "PE", "possible"),
    ("Return if fever persists", "fever", "conditional"),
    ("Discharge Instructions: Call if you have chest pain", "chest pain", "conditional"),
    ("[ ] Cough", "Cough", "present"),
    ("Denies chest pain but reports dyspnea", "chest pain", "absent"),
    ("Denies chest pain but reports dyspnea", "dyspnea", "present"),
    ("Start insulin if glucose > 200", "insulin", "conditional"),
    ("Possible migraine", "migraine", "possible"),
    ("Suspected infection", "infection", "possible"),
    ("Pneumonia ruled out", "Pneumonia", "absent"),
    ("Without nausea", "nausea", "absent"),
    ("Prior stroke", "stroke", "historical"),
    ("Resolved rash", "rash", "historical"),
    ("Medication discontinued", "Medication", "discontinued"),
    ("No known allergies", "allergies", "absent"),
    ("Father has hypertension", "hypertension", "family"),
    ("Sibling diagnosed with asthma", "asthma", "family"),
    ("Consider MRI", "MRI", "hypothetical"),
    ("If glucose rises, start insulin", "insulin", "conditional"),
    ("Call if symptoms worsen", "symptoms", "conditional"),
    ("Cough present", "Cough", "present"),
    ("No fever. Reports chills", "chills", "present"),
    ("Negative for vomiting", "vomiting", "absent"),
    ("History of asthma, currently stable", "asthma", "historical"),
    ("Return if fever persists", "fever", "conditional"),
]


def test_required_assertion_and_context_cases():
    assert len(ASSERTION_CASES) >= 30
    for note, term, expected in ASSERTION_CASES:
        section, assertion = _span(note, term)
        assert assertion.value == expected, (note, section, assertion)
    assert detect_experiencer("FAMILY HISTORY", "") == "family"
    assert detect_experiencer("unknown", "Husband has diabetes") == "other"
    assert detect_temporality(Assertion.HISTORICAL, "unknown") == "historical"
    assert detect_temporality(Assertion.CONDITIONAL, "unknown") == "planned"


def test_entity_group_mapping_never_promotes_non_present_values():
    expected = {
        "present": "confirmed-active",
        "absent": "denied-ruled-out",
        "family": "family",
        "historical": "historical-resolved",
        "discontinued": "historical-resolved",
        "possible": "uncertain-review",
        "conditional": "instructions-conditional",
        "hypothetical": "instructions-conditional",
    }
    for assertion, group in expected.items():
        assert derive_entity_group(assertion, status="approved") == group
    assert derive_entity_group("present", status="approved", evidence_verified=False) == "uncertain-review"
    assert derive_entity_group("present", status="approved", section="DISCHARGE INSTRUCTIONS") == "instructions-conditional"
    assert derive_exclusion_reason("[ ] Cough", 4) == "unchecked checklist item"


def test_evidence_matching_exact_hyphenation_whitespace_fuzzy_and_fabricated():
    assert locate_evidence("Patient has chest pain", "CHEST pain")["verified"]
    assert locate_evidence("long-term insulin", "long term insulin")["verified"]
    assert locate_evidence("no   fever\n or chills", "no fever or chills")["verified"]
    fuzzy = locate_evidence("patient reports dyspnea", "patient reports dyspnoea", fuzzy_threshold=0.80)
    assert fuzzy["verified"] and fuzzy["fuzzy"] and fuzzy["reason"]
    assert not locate_evidence("Patient reports cough", "fabricated chest pain")["verified"]


def test_provider_evidence_verifier_records_fuzzy_match_for_review(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "evidence_fuzzy_match_threshold", 0.80)
    entity = ExtractedEntity(
        type=EntityType.SYMPTOM, raw_text="dyspnea", normalized_value="dyspnea",
        code=None, code_system=None, confidence=0.9, assertion=Assertion.PRESENT,
        section=None, start_offset=0, end_offset=7, evidence_text="patient reports dyspnoea",
        page_number=1,
    )
    relocated, verified = verify_or_relocate_evidence("patient reports dyspnea", entity)
    assert verified
    assert relocated.details["evidence_fuzzy_match"] is True
    assert relocated.details["evidence_review_reason"]


def test_evidence_bbox_single_multi_missing_and_ocr_confidence():
    boxes = [
        {"start_offset": 0, "end_offset": 4, "bbox": [0.1, 0.2, 0.2, 0.3], "confidence": 0.8},
        {"start_offset": 5, "end_offset": 9, "bbox": [0.2, 0.25, 0.35, 0.35], "confidence": 0.6},
        {"start_offset": 10, "end_offset": 14, "bbox": [0.1, 0.4, 0.4, 0.5], "confidence": -1},
    ]
    assert evidence_bbox_and_confidence(boxes, 0, 4) == ([0.1, 0.2, 0.2, 0.3], 0.8)
    assert evidence_bbox_and_confidence(boxes, 0, 9) == ([0.1, 0.2, 0.35, 0.35], 0.7)
    assert evidence_bbox_and_confidence(boxes, 10, 14) == ([0.1, 0.4, 0.4, 0.5], None)
    assert evidence_bbox_and_confidence([], 0, 4) == (None, None)


def test_build_page_metadata_preserves_original_normalized_boxes():
    pages = [{"page_number": 1, "text": "chest pain", "word_boxes": [
        {"text": "chest", "start_offset": 0, "end_offset": 5, "bbox": [0.1, 0.2, 0.3, 0.4], "confidence": 0.9},
        {"text": "pain", "start_offset": 6, "end_offset": 10, "bbox": [0.31, 0.2, 0.5, 0.4], "confidence": 0.8},
    ]}]
    metadata = build_ocr_page_metadata("chest pain", pages)
    assert metadata[0]["word_boxes"][0]["bbox"] == [0.1, 0.2, 0.3, 0.4]
