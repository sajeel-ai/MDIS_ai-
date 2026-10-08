from .base import EntityData, ValidationIssue, issue

def validate(entity: EntityData, source_text: str) -> ValidationIssue | None:
    if entity.start_offset is None or entity.end_offset is None or entity.start_offset < 0 or entity.end_offset > len(source_text) or entity.end_offset <= entity.start_offset:
        return None
    if entity.evidence_text is None or source_text[entity.start_offset:entity.end_offset] != entity.evidence_text:
        return issue("EVIDENCE_EXACT", "error", "Evidence text does not exactly match its source offsets.")
    return None
