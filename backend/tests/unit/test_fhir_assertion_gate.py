"""Tests for FHIR assertion gate — Item 3.

Verifies that non-present entities (absent, hypothetical, conditional, etc.)
are never exported as FHIR Condition resources.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.fhir.fhir_service import build_document_fhir_bundle


def _make_entity(**kwargs: Any) -> MagicMock:
    """Build a minimal ClinicalEntity mock."""
    defaults = {
        "id": "00000000-0000-0000-0000-000000000099",
        "entity_type": "diagnosis",
        "assertion": "present",
        "status": "approved",
        "normalized_value": "Test condition",
        "raw_text": "test",
        "section": None,
        "details": {},
        "code": None,
        "code_system": None,
        "start_offset": 0,
        "end_offset": 4,
        "evidence_text": "test",
        "page_number": 1,
        "confidence": 0.9,
        "review_tasks": [],
    }
    defaults.update(kwargs)
    entity = MagicMock()
    for key, value in defaults.items():
        setattr(entity, key, value)
    return entity


def _make_document(entities: list) -> MagicMock:
    """Build a minimal Document mock with values that pass FHIR validation."""
    extraction = MagicMock()
    extraction.entities = entities

    patient = MagicMock()
    patient.id = "00000000-0000-0000-0000-000000000001"
    patient.mrn = "MRN001"
    patient.gender = "unknown"
    patient.first_name = None
    patient.last_name = None
    patient.dob = None

    doc = MagicMock()
    doc.id = "00000000-0000-0000-0000-000000000002"
    doc.patient = patient
    doc.patient_id = patient.id
    doc.mime_type = "application/pdf"
    doc.file_name = "test.pdf"
    doc.document_type = "discharge_summary"
    doc.extractions = [extraction]
    doc.created_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return doc


def _condition_count(bundle: dict) -> int:
    return sum(
        1
        for entry in bundle.get("entry", [])
        if entry.get("resource", {}).get("resourceType") == "Condition"
    )


def test_present_entity_exported() -> None:
    """A present, approved diagnosis is exported as a Condition."""
    entity = _make_entity(assertion="present", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 1


def test_absent_entity_not_exported() -> None:
    entity = _make_entity(assertion="absent", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 0


def test_hypothetical_entity_not_exported() -> None:
    entity = _make_entity(assertion="hypothetical", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 0


def test_conditional_entity_not_exported() -> None:
    """conditional is a new assertion value — must not produce a Condition."""
    entity = _make_entity(assertion="conditional", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 0


def test_possible_entity_not_exported() -> None:
    entity = _make_entity(assertion="possible", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 0


def test_family_entity_not_exported() -> None:
    entity = _make_entity(assertion="family", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 0


def test_historical_entity_not_exported() -> None:
    entity = _make_entity(assertion="historical", status="approved")
    doc = _make_document([entity])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 0


def test_mixed_present_and_absent() -> None:
    """Only the present entity becomes a Condition."""
    present = _make_entity(assertion="present", status="approved", normalized_value="Hypertension")
    absent = _make_entity(assertion="absent", status="approved", normalized_value="Pneumonia")
    doc = _make_document([present, absent])
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    assert _condition_count(bundle) == 1

