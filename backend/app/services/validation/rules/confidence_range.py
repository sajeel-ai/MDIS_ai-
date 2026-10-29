from .base import EntityData, ValidationIssue, issue

def validate(entity: EntityData) -> ValidationIssue | None:
    # None is the explicit "not available" value; it is not a malformed
    # measurement. If a score exists, it must still satisfy the range.
    if entity.confidence is not None and not 0 <= float(entity.confidence) <= 1:
        return issue("CONFIDENCE_RANGE", "error", "Model confidence must be within 0 and 1.")
    return None
