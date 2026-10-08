from .base import EntityData, ValidationIssue, issue

def validate(entity: EntityData) -> ValidationIssue | None:
    if not entity.entity_type or not entity.raw_text or not entity.normalized_value or not entity.normalized_value.strip():
        return issue("REQUIRED_FIELDS", "error", "Entity type, source text, and normalized value are required.")
    return None
