import re
from .base import EntityData, ValidationIssue, issue

NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
UNIT = re.compile(r"\b(?:mmol/L|mg/dL|g/dL|mEq/L|U/L|IU/L|%|cells/uL|10\^\d+/L)\b", re.I)

def validate(entity: EntityData) -> ValidationIssue | None:
    if entity.entity_type.lower() not in {"lab_result", "lab"}: return None
    details = entity.details or {}
    text = " ".join(str(v) for v in (details.get("value"), details.get("unit"), entity.normalized_value, entity.raw_text) if v)
    if not NUMBER.search(text) or not UNIT.search(text):
        return issue("LAB_VALUE_UNIT", "warning", "Lab result should include a numeric value and unit.")
    return None
