from .base import EntityData, ValidationIssue, issue

def validate(entity: EntityData) -> ValidationIssue | None:
    if entity.confidence is None or not 0 <= float(entity.confidence) <= 1:
        return issue("CONFIDENCE_RANGE", "error", "Model confidence must be within 0 and 1.")
    return None
