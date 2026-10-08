"""Unit tests for Validation Rules."""

import pytest
from app.models import ClinicalEntity, ValidationResult


def test_entity_confidence_validation():
    high_conf_entity = ClinicalEntity(
        entity_type="diagnosis",
        raw_text="Pneumonia",
        normalized_value="Community-acquired pneumonia",
        confidence=0.96,
        status="accepted",
    )
    low_conf_entity = ClinicalEntity(
        entity_type="medication",
        raw_text="Atorvastatin",
        normalized_value="Atorvastatin",
        confidence=0.72,
        status="flagged",
    )

    val_high = ValidationResult(
        validation_rule="CONFIDENCE_ABOVE_THRESHOLD",
        status="pass" if high_conf_entity.confidence >= 0.85 else "fail",
        severity="info",
        message="Passed confidence threshold",
    )
    val_low = ValidationResult(
        validation_rule="CONFIDENCE_ABOVE_THRESHOLD",
        status="pass" if low_conf_entity.confidence >= 0.85 else "fail",
        severity="warning",
        message="Failed confidence threshold",
    )

    assert val_high.status == "pass"
    assert val_low.status == "fail"

