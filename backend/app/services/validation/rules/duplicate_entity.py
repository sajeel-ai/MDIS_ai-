from collections import Counter
from .base import EntityData, ValidationIssue, issue

def duplicate_keys(entities: list[EntityData]) -> set[tuple[str, str, str, str]]:
    keys = [(e.entity_type.casefold(), (e.normalized_value or "").strip().casefold(), e.assertion, (e.section or "").casefold()) for e in entities]
    return {key for key, count in Counter(keys).items() if key[1] and count > 1}

def validate(entity: EntityData, duplicates: set[tuple[str, str, str, str]]) -> ValidationIssue | None:
    key = (entity.entity_type.casefold(), (entity.normalized_value or "").strip().casefold(), entity.assertion, (entity.section or "").casefold())
    if key in duplicates: return issue("DUPLICATE_ENTITY", "warning", "The same normalized entity occurs more than once in this document.")
    return None
