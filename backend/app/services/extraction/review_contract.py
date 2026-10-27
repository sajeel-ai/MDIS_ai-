"""Review contract helpers; null means the pipeline did not measure a value."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


def normalize_evidence_text(value: str) -> str:
    value = value.casefold().replace("\u00ad", "")
    value = re.sub(r"[-‐‑‒–—]+", " ", value)
    return " ".join(value.split())


def locate_evidence(source_text: str, evidence_text: str, *, fuzzy_threshold: float = 1.0) -> dict[str, Any]:
    """Locate normalized exact evidence, or report a high-threshold fuzzy window."""
    source_chars: list[str] = []
    source_offsets: list[int] = []
    for index, char in enumerate(source_text):
        replacement = " " if char in "-‐‑‒–—" or char.isspace() else char.casefold()
        for item in replacement:
            if item == " " and (not source_chars or source_chars[-1] == " "):
                continue
            source_chars.append(item)
            source_offsets.append(index)
    left_trim = 0
    while left_trim < len(source_chars) and source_chars[left_trim] == " ":
        left_trim += 1
    right_trim = len(source_chars)
    while right_trim > left_trim and source_chars[right_trim - 1] == " ":
        right_trim -= 1
    source_chars = source_chars[left_trim:right_trim]
    source_offsets = source_offsets[left_trim:right_trim]
    source_normalized = "".join(source_chars)
    needle = normalize_evidence_text(evidence_text)
    if not needle:
        return {"verified": False, "reason": "evidence not found"}
    index = source_normalized.find(needle)
    if index >= 0:
        return {"verified": True, "fuzzy": False, "start": source_offsets[index], "end": source_offsets[index + len(needle) - 1] + 1}
    if fuzzy_threshold < 1.0:
        import re
        words = list(re.finditer(r"\S+", source_normalized))
        needle_words = needle.split()
        width = len(needle_words)
        candidates = []
        for offset in range(max(0, len(words) - width + 1)):
            chunk = " ".join(match.group() for match in words[offset:offset + width])
            score = SequenceMatcher(None, needle, chunk).ratio()
            if score >= fuzzy_threshold:
                candidates.append((score, offset, offset + width - 1))
        if candidates:
            score, first, last = max(candidates)
            start_n, end_n = words[first].start(), words[last].end()
            return {"verified": True, "fuzzy": True, "score": score, "start": source_offsets[start_n], "end": source_offsets[end_n - 1] + 1, "reason": "evidence fuzzy matched; reviewer confirmation required"}
    return {"verified": False, "fuzzy": False, "reason": "evidence not found"}


def verify_evidence(source_text: str, evidence_text: str, *, fuzzy_threshold: float = 0.97) -> dict[str, Any]:
    """Match evidence in OCR source; fuzzy matches are explicit and never silent."""
    return locate_evidence(source_text, evidence_text, fuzzy_threshold=fuzzy_threshold)


def derive_entity_group(
    assertion: str | None,
    *,
    status: str | None = None,
    section: str | None = None,
    evidence_verified: bool | None = None,
    unresolved_flag: bool = False,
) -> str:
    """Map an entity to a review group without promoting non-present findings."""
    assertion = (assertion or "").lower()
    status = (status or "").lower()
    section = (section or "").upper()
    if evidence_verified is False or unresolved_flag or status in {"needs_correction", "needs_review"}:
        return "uncertain-review"
    if assertion == "family" or section == "FAMILY HISTORY":
        return "family"
    if assertion == "absent":
        return "denied-ruled-out"
    if assertion in {"historical", "discontinued"}:
        return "historical-resolved"
    if assertion in {"conditional", "hypothetical"} or section == "DISCHARGE INSTRUCTIONS":
        return "instructions-conditional"
    if assertion == "present":
        return "confirmed-active"
    if assertion in {"possible", "uncertain"}:
        return "uncertain-review"
    return "uncertain-review"


def derive_exclusion_reason(text: str, start_offset: int) -> str | None:
    """Retain unchecked checklist items with an explicit, reviewable reason."""
    prefix = text[max(0, start_offset - 12):start_offset]
    if re.search(r"\[\s\]\s*$", prefix):
        return "unchecked checklist item"
    return None


def build_ocr_page_metadata(source_text: str, pages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Attach OCR word offsets to the persisted full-document text coordinate space."""
    result = []
    cursor = 0
    for page in pages or []:
        page_text = str(page.get("text") or "")
        if not page_text:
            continue
        page_start = source_text.find(page_text, cursor)
        if page_start < 0:
            # Text-layer pages may have layout normalization differences; without
            # a reliable correspondence, retain page data but no guessed offsets.
            result.append({"page_number": page.get("page_number"), "word_boxes": []})
            continue
        page_end = page_start + len(page_text)
        cursor = page_end
        words = []
        for word in page.get("word_boxes") or []:
            word_text = str(word.get("text") or "")
            bbox = word.get("bbox")
            if not word_text or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            local_start = page_text.find(word_text)
            if local_start < 0:
                continue
            # OCR words can repeat. Advance through repeated tokens in output order.
            search_cursor = words[-1]["end_offset"] - page_start if words else 0
            local_start = page_text.find(word_text, max(0, search_cursor))
            if local_start < 0:
                continue
            item = {
                "text": word_text,
                "start_offset": page_start + local_start,
                "end_offset": page_start + local_start + len(word_text),
                "bbox": [max(0.0, min(1.0, float(value))) for value in bbox],
                "confidence": word.get("confidence"),
            }
            words.append(item)
        result.append({"page_number": page.get("page_number"), "text_start": page_start, "text_end": page_end, "word_boxes": words})
    return result


def evidence_bbox_and_confidence(
    word_boxes: list[dict[str, Any]] | None,
    start_offset: int,
    end_offset: int,
) -> tuple[list[float] | None, float | None]:
    """Union normalized boxes overlapping a text span and average measured OCR confidence."""
    selected = []
    for word in word_boxes or []:
        begin, end = word.get("start_offset"), word.get("end_offset")
        if not isinstance(begin, int) or not isinstance(end, int) or end <= start_offset or begin >= end_offset:
            continue
        bbox = word.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            selected.append((bbox, word.get("confidence")))
    if not selected:
        return None, None
    bbox = [
        max(0.0, min(float(box[0]) for box, _ in selected)),
        max(0.0, min(float(box[1]) for box, _ in selected)),
        min(1.0, max(float(box[2]) for box, _ in selected)),
        min(1.0, max(float(box[3]) for box, _ in selected)),
    ]
    confidences = [float(value) for _, value in selected if value is not None and float(value) >= 0]
    confidence = sum(confidences) / len(confidences) if confidences else None
    return bbox, confidence
