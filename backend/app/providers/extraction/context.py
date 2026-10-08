"""Deterministic section and assertion context for local term matches."""

import re

from app.schemas.entity_contract import Assertion


SECTION_ALIASES = {
    "FAMILY HISTORY": "FAMILY HISTORY",
    "FAMILY MEDICAL HISTORY": "FAMILY HISTORY",
    "PAST MEDICAL HISTORY": "PAST MEDICAL HISTORY",
    "PMH": "PAST MEDICAL HISTORY",
    "ALLERGIES": "ALLERGIES",
    "ALLERGY": "ALLERGIES",
    "MEDICATIONS ON DISCHARGE": "MEDICATIONS ON DISCHARGE",
    "DISCHARGE MEDICATIONS": "MEDICATIONS ON DISCHARGE",
    "MEDICATIONS": "MEDICATIONS",
    "ASSESSMENT": "ASSESSMENT",
    "DIAGNOSIS": "DIAGNOSIS",
    "HISTORY OF PRESENT ILLNESS": "HISTORY OF PRESENT ILLNESS",
    "HPI": "HISTORY OF PRESENT ILLNESS",
    "REVIEW OF SYSTEMS": "REVIEW OF SYSTEMS",
    "PLAN": "PLAN",
    "LABORATORY": "LABORATORY",
    "LAB RESULTS": "LABORATORY",
}

_SECTION_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /_-]{1,50})\s*:?\s*$")
_BOUNDARY_RE = re.compile(r";|\bbut\b|\bhowever\b|[.!?\n]", re.IGNORECASE)
_FAMILY_RE = re.compile(r"\b(?:mother|father|sibling|brother|sister|family history)\b", re.IGNORECASE)
_HISTORICAL_RE = re.compile(r"\b(?:history of|h/o|previously|resolved)\b", re.IGNORECASE)
_HYPOTHETICAL_RE = re.compile(r"\b(?:if|should|return if)\b", re.IGNORECASE)
_POSSIBLE_RE = re.compile(r"\b(?:possible|suspected|probable|rule out)\b|\?", re.IGNORECASE)
_ABSENT_RE = re.compile(r"\b(?:no evidence of|negative for|denies|without|ruled out|no)\b", re.IGNORECASE)


def detect_section(text: str, offset: int) -> str | None:
    current = None
    line_start = 0
    for line in text[:offset].splitlines(keepends=True):
        content = line.strip()
        candidate = content.split(":", 1)[0].strip()
        match = _SECTION_RE.match(candidate)
        heading = re.sub(r"\s+", " ", match.group(1).strip().rstrip(":")) if match else ""
        if heading.upper() in SECTION_ALIASES:
            current = SECTION_ALIASES[heading.upper()]
        line_start += len(line)

    # Also support inline heading forms such as "ALLERGIES: medication".
    prefix = text[line_start:offset]
    if ":" in prefix:
        candidate = prefix.split(":", 1)[0].strip()
        heading = re.sub(r"\s+", " ", candidate).upper()
        if heading in SECTION_ALIASES:
            current = SECTION_ALIASES[heading]
    return current


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    right = len(text)
    for match in _BOUNDARY_RE.finditer(text):
        if match.end() <= start:
            left = match.end()
        elif match.start() >= end:
            right = match.start()
            break
    return left, right


def detect_assertion(text: str, start: int, end: int, section: str | None = None) -> Assertion:
    left, right = _clause_bounds(text, start, end)
    clause = text[left:right]
    relative_start = start - left
    before = clause[:relative_start]
    after = clause[relative_start + (end - start):]

    if _HYPOTHETICAL_RE.search(before) or _HYPOTHETICAL_RE.search(after):
        return Assertion.HYPOTHETICAL
    if section == "FAMILY HISTORY" or _FAMILY_RE.search(before) or _FAMILY_RE.search(after):
        return Assertion.FAMILY
    if section == "PAST MEDICAL HISTORY" or _HISTORICAL_RE.search(before) or _HISTORICAL_RE.search(after):
        return Assertion.HISTORICAL
    if _POSSIBLE_RE.search(before) or _POSSIBLE_RE.search(after) or text[end:end + 1] == "?" or text[start - 1:start] == "?":
        return Assertion.POSSIBLE
    if _ABSENT_RE.search(before) or _ABSENT_RE.search(after) or re.search(r"\b(?:absent)\b", after, re.IGNORECASE):
        return Assertion.ABSENT
    return Assertion.PRESENT
