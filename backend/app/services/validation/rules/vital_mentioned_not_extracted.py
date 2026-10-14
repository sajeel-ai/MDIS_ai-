"""Rule: vital_mentioned_not_extracted

Detects vital-sign terms in source text where no vital entity was extracted,
recording a document-level validation flag.
"""

import re
from typing import TypedDict
from .base import EntityData, ValidationIssue, issue


class MissingVitalFlag(TypedDict):
    flag: str
    vital_term: str
    start_offset: int
    end_offset: int
    evidence: str


# Vital terms to check as specified in Item 2
VITAL_TERMS = [
    ("blood pressure", re.compile(r"\b(?:blood\s+pressure|bp|b/p)\b", re.I), "Blood pressure"),
    ("pulse", re.compile(r"\bpulse\b", re.I), "Heart rate"),
    ("heart rate", re.compile(r"\bheart\s+rate\b", re.I), "Heart rate"),
    ("temperature", re.compile(r"\btemperature\b", re.I), "Body temperature"),
    ("spo2", re.compile(r"\bspo2\b", re.I), "Oxygen saturation"),
    ("oxygen saturation", re.compile(r"\boxygen\s+saturation\b", re.I), "Oxygen saturation"),
    ("respiratory rate", re.compile(r"\brespiratory\s+rate\b", re.I), "Respiratory rate"),
    ("weight", re.compile(r"\bweight\b", re.I), "Body weight"),
    ("height", re.compile(r"\bheight\b", re.I), "Body height"),
    ("vitals", re.compile(r"\bvitals?\b", re.I), "Vitals"),
]

# Patterns for advice, instructions, conditional mentions, or past history.
# Notice 'record' alone must not match 'not recorded'. We use strict patterns.
ADVICE_OR_HISTORY_RE = re.compile(
    r"\b(?:history\s+of|h/o|check|monitor|recheck|follow\s*up|measure|target|goal|at\s+home|home\s+bp|prior|past|recommend(?:ed)?|advised|should|if|return\s+if)\b",
    re.I,
)


def _is_advice_or_history(text: str, start: int, end: int) -> bool:
    """Check if the vital term occurs in an advice, conditional, or historical context."""
    # Look at a window around the match (sentence / clause boundaries)
    left = max(0, start - 50)
    right = min(len(text), end + 50)
    # Restrict to sentence or line if possible
    clause = re.split(r"[\n;.]", text[left:start])[-1] + text[start:end] + re.split(r"[\n;.]", text[end:right])[0]
    return bool(ADVICE_OR_HISTORY_RE.search(clause))


def detect_missing_vitals(source_text: str, entities: list[EntityData]) -> list[MissingVitalFlag]:
    """Detect vital-sign terms in source_text that have no extracted vital entity.
    Never raises on any input.
    """
    try:
        if not source_text or not isinstance(source_text, str) or not source_text.strip():
            return []

        # Collect normalized values of already extracted vitals
        extracted_vitals = {
            (e.normalized_value or "").strip().casefold()
            for e in (entities or [])
            if getattr(e, "entity_type", "").lower() == "vital"
        }

        # Also map vital terms to their standard normalized names
        flags: list[MissingVitalFlag] = []

        for term_label, pattern, norm_name in VITAL_TERMS:
            # If this vital concept was already extracted anywhere with a value, skip flagging
            if norm_name != "Vitals" and norm_name.casefold() in extracted_vitals:
                continue
            if norm_name == "Vitals" and bool(extracted_vitals):
                continue

            for match in pattern.finditer(source_text):
                start, end = match.start(), match.end()

                # Check if this occurrence is inside advice, conditional, or history text
                if _is_advice_or_history(source_text, start, end):
                    continue

                # Check if an extracted vital entity covers this exact span or nearby
                if any(
                    getattr(e, "entity_type", "").lower() == "vital"
                    and getattr(e, "start_offset", None) is not None
                    and getattr(e, "end_offset", None) is not None
                    and not (e.end_offset <= start or e.start_offset >= end)
                    for e in (entities or [])
                ):
                    continue

                # Capture context evidence snippet
                ev_start = max(0, start - 20)
                ev_end = min(len(source_text), end + 30)
                evidence = source_text[ev_start:ev_end].strip()

                flags.append({
                    "flag": "vital_mentioned_not_extracted",
                    "vital_term": term_label,
                    "start_offset": start,
                    "end_offset": end,
                    "evidence": evidence,
                })

        return flags
    except Exception:
        return []


def validate_document_vitals(source_text: str, entities: list[EntityData]) -> list[ValidationIssue]:
    """Return ValidationIssue items for document-level missing vital signs.
    Never raises on any input.
    """
    try:
        flags = detect_missing_vitals(source_text, entities)
        issues: list[ValidationIssue] = []
        for f in flags:
            issues.append(
                issue(
                    "vital_mentioned_not_extracted",
                    "warning",
                    f"Vital sign '{f['vital_term']}' mentioned but no value extracted (offset {f['start_offset']}-{f['end_offset']}).",
                )
            )
        return issues
    except Exception:
        return []
