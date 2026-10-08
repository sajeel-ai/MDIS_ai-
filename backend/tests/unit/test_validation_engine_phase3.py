from app.services.validation.rules.base import EntityData
from app.services.validation.rules import (
    code_system_format, confidence_range, date_plausible, duplicate_entity,
    evidence_bounds, evidence_exact, lab_value_unit, med_dose_unit,
    required_fields, conflict,
)
from app.services.validation.engine import validate_entities
from app.services.validation.review_policy import requires_review
from app.schemas.entity_contract import ExtractedEntity


def entity(**updates):
    values = dict(entity_type="diagnosis", raw_text="pneumonia", normalized_value="pneumonia", confidence=.9)
    values.update(updates)
    return EntityData(**values)


def test_required_fields_pass_and_fail():
    assert required_fields.validate(entity()) is None
    assert required_fields.validate(entity(normalized_value=" ")).rule_code == "REQUIRED_FIELDS"


def test_evidence_bounds_pass_and_fail():
    assert evidence_bounds.validate(entity(start_offset=0, end_offset=4), "text") is None
    assert evidence_bounds.validate(entity(start_offset=0, end_offset=5), "text").rule_code == "EVIDENCE_BOUNDS"


def test_evidence_exact_pass_and_fail():
    valid = entity(start_offset=0, end_offset=4, evidence_text="text")
    invalid = entity(start_offset=0, end_offset=4, evidence_text="nope")
    assert evidence_exact.validate(valid, "text") is None
    assert evidence_exact.validate(invalid, "text").rule_code == "EVIDENCE_EXACT"


def test_confidence_range_pass_and_fail():
    assert confidence_range.validate(entity(confidence=.5)) is None
    assert confidence_range.validate(entity(confidence=1.1)).rule_code == "CONFIDENCE_RANGE"


def test_code_system_format_pass_and_fail():
    assert code_system_format.validate(entity(details={"code": "J18.9", "code_system": "ICD10"})) is None
    assert code_system_format.validate(entity(details={"code": "bad code", "code_system": "ICD10"})).rule_code == "CODE_SYSTEM_FORMAT"


def test_med_dose_unit_pass_and_fail():
    assert med_dose_unit.validate(entity(entity_type="medication", raw_text="500 mg", details={"dose": "500 mg"})) is None
    assert med_dose_unit.validate(entity(entity_type="medication", raw_text="500 xyz", details={"dose": "500 xyz"})).rule_code == "MED_DOSE_UNIT"
    assert med_dose_unit.validate(entity(entity_type="medication", raw_text="Drug name")).rule_code == "MED_DOSE_UNIT"


def test_lab_value_unit_pass_and_fail():
    assert lab_value_unit.validate(entity(entity_type="lab", raw_text="5 mmol/L")) is None
    assert lab_value_unit.validate(entity(entity_type="lab", raw_text="glucose elevated")).rule_code == "LAB_VALUE_UNIT"


def test_date_plausible_pass_and_fail():
    assert date_plausible.validate(entity(raw_text="2024-02-29")) is None
    assert date_plausible.validate(entity(raw_text="2023-02-29")).rule_code == "DATE_PLAUSIBLE"


def test_duplicate_rule_pass_and_fail():
    first = entity()
    duplicate = duplicate_entity.duplicate_keys([first, entity()])
    assert duplicate_entity.validate(first, duplicate).rule_code == "DUPLICATE_ENTITY"
    assert duplicate_entity.validate(first, set()) is None


def test_conflict_rule_detects_present_absent():
    found = conflict.conflicts([entity(), entity(assertion="absent")])
    assert {result.rule_code for result in found.values()} == {"CONFLICT"}
    assert conflict.conflicts([entity()]) == {}


def test_conflict_rule_detects_medication_dose_difference():
    left = entity(entity_type="medication", normalized_value="drug", details={"dose": "5 mg"})
    right = entity(entity_type="medication", normalized_value="drug", details={"dose": "10 mg"})
    assert {result.rule_code for result in conflict.conflicts([left, right]).values()} == {"CONFLICT"}


def test_policy_all_and_threshold_forced_review():
    assert requires_review(entity(confidence=.99), [], policy="all", threshold=.8)
    assert not requires_review(entity(confidence=.99), [], policy="threshold", threshold=.8)
    assert requires_review(entity(confidence=.99, assertion="absent"), [], policy="threshold", threshold=.8)
    assert requires_review(entity(confidence=.99, entity_type="medication"), [], policy="threshold", threshold=.8)
    assert requires_review(entity(confidence=.7), [], policy="threshold", threshold=.8)
    assert requires_review(entity(confidence=.99), [type("Finding", (), {"severity": "warning"})()], policy="threshold", threshold=.8)


def test_engine_marks_document_level_conflicts():
    def candidate(assertion):
        return ExtractedEntity.model_validate({
            "type": "diagnosis", "raw_text": "diabetes", "normalized_value": "diabetes",
            "code": None, "code_system": None, "confidence": .9, "assertion": assertion,
            "section": None, "start_offset": 0, "end_offset": 8, "evidence_text": "diabetes", "page_number": 1,
        })
    result = validate_entities("diabetes", [candidate("present"), candidate("absent")])
    assert all(any(issue.rule_code == "CONFLICT" for issue in issues) for issues in result)
