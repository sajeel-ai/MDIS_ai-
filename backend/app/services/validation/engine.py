from app.schemas.entity_contract import ExtractedEntity
from .rules.base import EntityData, ValidationIssue
from .rules import (
    code_system_format, confidence_range, date_plausible, duplicate_entity,
    evidence_bounds, evidence_exact, lab_value_unit, med_dose_unit,
    required_fields, conflict,
)


def validate_entities(source_text: str, items: list[ExtractedEntity]) -> list[list[ValidationIssue]]:
    entities = [EntityData(
        entity_type=item.type.value,
        raw_text=getattr(item, "raw_text", item.evidence_text),
        normalized_value=item.normalized_value,
        confidence=item.confidence,
        assertion=item.assertion.value,
        section=item.section,
        details={"code": item.code, "code_system": item.code_system.value if item.code_system else None},
        start_offset=item.start_offset,
        end_offset=item.end_offset,
        evidence_text=item.evidence_text,
    ) for item in items]
    duplicates = duplicate_entity.duplicate_keys(entities)
    conflicts = conflict.conflicts(entities)
    results: list[list[ValidationIssue]] = []
    for index, entity in enumerate(entities):
        issues = [rule for rule in (
            required_fields.validate(entity),
            evidence_bounds.validate(entity, source_text),
            evidence_exact.validate(entity, source_text),
            confidence_range.validate(entity),
            code_system_format.validate(entity),
            med_dose_unit.validate(entity),
            lab_value_unit.validate(entity),
            date_plausible.validate(entity),
            duplicate_entity.validate(entity, duplicates),
            conflicts.get(index),
        ) if rule is not None]
        results.append(issues)
    return results
