"""Tests for implicit findings extraction — Item 5."""

import asyncio
import pytest

from app.providers.extraction.local import LocalExtractionProvider


def _extract(text: str):
    provider = LocalExtractionProvider()
    return asyncio.run(provider.extract_clinical_entities(text))


def _entities_of_type(text: str, entity_type: str):
    result = _extract(text)
    return [e for e in result["entities"] if e["type"] == entity_type]


def test_poorly_controlled_sugars() -> None:
    """'poorly controlled sugars' → entity with normalized='Poorly controlled blood glucose'."""
    result = _extract("poorly controlled sugars")
    found = [e for e in result["entities"] if "Poorly controlled blood glucose" in e["normalized_value"]]
    assert found, f"Expected implicit finding for 'poorly controlled sugars', got {result['entities']}"


def test_fluid_overloaded() -> None:
    """'patient is fluid overloaded' → entity found."""
    result = _extract("patient is fluid overloaded")
    found = [e for e in result["entities"] if "Fluid overload" in e["normalized_value"]]
    assert found, f"Expected implicit finding for 'fluid overloaded', got {result['entities']}"


def test_on_supplemental_oxygen() -> None:
    """'patient is on supplemental oxygen' → entity with normalized='Oxygen-dependent'."""
    result = _extract("patient is on supplemental oxygen")
    found = [e for e in result["entities"] if "Oxygen-dependent" in e["normalized_value"]]
    assert found, f"Expected implicit finding for 'on supplemental oxygen', got {result['entities']}"


def test_negated_fluid_overload() -> None:
    """'no evidence of fluid overload' → entity found but assertion='absent'."""
    result = _extract("no evidence of fluid overload")
    found = [e for e in result["entities"] if "Fluid overload" in e["normalized_value"]]
    assert found, f"Expected implicit finding for 'fluid overload' even when negated"
    assert found[0]["assertion"] == "absent", (
        f"Expected assertion='absent', got {found[0]['assertion']!r}"
    )


def test_no_implicit_findings_in_normal_text() -> None:
    """Plain clinical text without implicit findings produces no implicit entities."""
    text = "Patient presents with cough and fever. No other complaints."
    result = _extract(text)
    # Only the normal symptom entities should be present — none from IMPLICIT_FINDINGS
    implicit_normalized = {
        "Poorly controlled blood glucose",
        "Fluid overload",
        "Oxygen-dependent",
        "Agonal respirations",
        "Elevated blood glucose",
    }
    implicit_found = [
        e for e in result["entities"] if e["normalized_value"] in implicit_normalized
    ]
    assert not implicit_found, (
        f"Expected no implicit findings in plain text, got {implicit_found}"
    )

