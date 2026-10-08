import re
from .base import EntityData, ValidationIssue, issue

FORMATS = {
    "ICD10": r"^[A-Z][0-9][A-Z0-9](?:\.[A-Z0-9]{1,4})?$",
    "ICD-10": r"^[A-Z][0-9][A-Z0-9](?:\.[A-Z0-9]{1,4})?$",
    "ICD-10-CM": r"^[A-Z][0-9][A-Z0-9](?:\.[A-Z0-9]{1,4})?$",
    "SNOMED-CT": r"^\d{6,18}$", "SNOMED": r"^\d{6,18}$",
    "LOINC": r"^\d{1,7}-\d$", "CPT": r"^\d{5}$", "RXNORM": r"^\d+$",
}

def validate(entity: EntityData) -> ValidationIssue | None:
    details = entity.details or {}
    code, system = details.get("code"), details.get("code_system")
    if not code and not system:
        return None
    pattern = FORMATS.get(str(system or "").upper())
    if not code or not pattern or not re.fullmatch(pattern, str(code).strip(), re.I):
        return issue("CODE_SYSTEM_FORMAT", "warning", "Code or code system does not match a supported format.")
    return None
