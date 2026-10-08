import re
from .base import EntityData, ValidationIssue, issue

UNITS = {"mg", "mcg", "μg", "ug", "g", "kg", "ml", "l", "meq", "mmol", "units", "iu", "unit", "tablet", "tablets", "capsule", "capsules"}
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*([a-zA-Zμ]+)\b")

def validate(entity: EntityData) -> ValidationIssue | None:
    if entity.entity_type.lower() != "medication": return None
    details = entity.details or {}
    value = str(details.get("dose") or entity.raw_text or "")
    match = DOSE.search(value)
    if not match or match.group(1).casefold() not in UNITS:
        return issue("MED_DOSE_UNIT", "warning", "Medication dose must include a number and a unit from the supported allowlist.")
    return None
