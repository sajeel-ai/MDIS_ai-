from collections import defaultdict
from .base import EntityData, ValidationIssue, issue

def conflicts(entities: list[EntityData]) -> dict[int, ValidationIssue]:
    groups: dict[tuple[str, str], list[tuple[int, EntityData]]] = defaultdict(list)
    for index, entity in enumerate(entities):
        groups[(entity.entity_type.casefold(), (entity.normalized_value or "").strip().casefold())].append((index, entity))
    found = {}
    for group in groups.values():
        assertions = {entity.assertion for _, entity in group}
        doses = {(entity.details or {}).get("dose") for _, entity in group if entity.entity_type.casefold() == "medication"}
        conflict = ("present" in assertions and "absent" in assertions) or (len(doses) > 1)
        if conflict:
            for index, _ in group:
                found[index] = issue("CONFLICT", "warning", "Conflicting assertions or medication doses occur for this concept in one document.")
    return found
