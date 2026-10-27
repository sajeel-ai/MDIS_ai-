"""Tests for assertion/negation detection in context.py — Item 1 & 2."""

import pytest

from app.providers.extraction.context import detect_assertion
from app.schemas.entity_contract import Assertion


@pytest.mark.parametrize(
    "text, start, end, expected",
    [
        # Standard pre-entity negation
        ("denies chest pain", 7, 17, Assertion.ABSENT),
        # "no" before historical → negation wins
        ("no history of MI", 14, 16, Assertion.ABSENT),
        # Post-entity colon-negation  (NEW — currently fails)
        ("chest pain: negative", 0, 10, Assertion.ABSENT),
        # no evidence of
        ("no evidence of pneumonia", 15, 24, Assertion.ABSENT),
        # Conditional (NEW — currently fails: CONDITIONAL doesn't exist)
        ("if fever persists", 3, 8, Assertion.CONDITIONAL),
        # Rule-out → possible
        ("rule out PE", 9, 11, Assertion.POSSIBLE),
        # Family history
        ("family history of diabetes", 18, 26, Assertion.FAMILY),
        # Normal present
        ("patient has chest pain", 12, 22, Assertion.PRESENT),
        # Possible
        ("possible pneumonia", 9, 18, Assertion.POSSIBLE),
        # Historical
        ("history of hypertension", 11, 23, Assertion.HISTORICAL),
    ],
)
def test_detect_assertion(text: str, start: int, end: int, expected: Assertion) -> None:
    result = detect_assertion(text, start, end, section=None)
    assert result == expected, (
        f"Text={text!r} span=[{start}:{end}]={text[start:end]!r}: "
        f"expected {expected.value!r}, got {result.value!r}"
    )


@pytest.mark.parametrize(
    "text,entity,expected",
    [
        ("no fever or chills", "fever", Assertion.ABSENT),
        ("no fever or chills", "chills", Assertion.ABSENT),
        ("denies chest pain but reports dyspnea", "chest pain", Assertion.ABSENT),
        ("denies chest pain but reports dyspnea", "dyspnea", Assertion.PRESENT),
        ("chest pain ruled out", "chest pain", Assertion.ABSENT),
        ("no signs of infection", "infection", Assertion.ABSENT),
        ("father had MI", "MI", Assertion.FAMILY),
        ("history of asthma, currently stable", "asthma", Assertion.HISTORICAL),
        ("start insulin if glucose > 200", "insulin", Assertion.HYPOTHETICAL),
        ("patient reports nausea", "nausea", Assertion.PRESENT),
        ("negative for vomiting", "vomiting", Assertion.ABSENT),
        ("without cough", "cough", Assertion.ABSENT),
        ("possible appendicitis", "appendicitis", Assertion.POSSIBLE),
        ("rule out pulmonary embolism", "pulmonary embolism", Assertion.POSSIBLE),
        ("mother has breast cancer", "breast cancer", Assertion.FAMILY),
        ("sibling diagnosed with asthma", "asthma", Assertion.FAMILY),
        ("previously had pneumonia", "pneumonia", Assertion.HISTORICAL),
        ("resolved headache", "headache", Assertion.HISTORICAL),
        ("if fever develops", "fever", Assertion.CONDITIONAL),
        ("return if pain worsens", "pain", Assertion.CONDITIONAL),
        ("no evidence of fracture", "fracture", Assertion.ABSENT),
        ("denied shortness of breath", "shortness of breath", Assertion.ABSENT),
        ("reports dyspnea; denies chest pain", "dyspnea", Assertion.PRESENT),
        ("reports dyspnea; denies chest pain", "chest pain", Assertion.ABSENT),
        ("no longer taking warfarin", "warfarin", Assertion.DISCONTINUED),
        ("aspirin was discontinued", "aspirin", Assertion.DISCONTINUED),
        ("history of diabetes", "diabetes", Assertion.HISTORICAL),
        ("FAMILY HISTORY: father with MI", "MI", Assertion.FAMILY),
        ("start antibiotics tomorrow", "antibiotics", Assertion.HYPOTHETICAL),
        ("fever is absent", "fever", Assertion.ABSENT),
    ],
)
def test_extended_assertion_contexts(text: str, entity: str, expected: Assertion) -> None:
    start = text.lower().index(entity.lower())
    assert detect_assertion(text, start, start + len(entity), section=None) == expected

