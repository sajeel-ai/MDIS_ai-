from .base import EntityData, ValidationIssue, issue

def validate(entity: EntityData, source_text: str) -> ValidationIssue | None:
    start, end = entity.start_offset, entity.end_offset
    if start is None or end is None or start < 0 or end <= start or end > len(source_text):
        return issue("EVIDENCE_BOUNDS", "error", "Evidence offsets are outside the source text bounds.")
    return None
