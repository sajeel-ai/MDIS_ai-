from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    rule_code: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EntityData:
    entity_type: str
    raw_text: str | None
    normalized_value: str | None
    confidence: float | None
    assertion: str = "present"
    section: str | None = None
    details: dict[str, Any] | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    evidence_text: str | None = None


def issue(code: str, severity: str, message: str, details: dict[str, Any] | None = None) -> ValidationIssue:
    return ValidationIssue(code, severity, message, details or {})
