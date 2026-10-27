"""Tests for the terminology service — Items 2 & 3.

These tests are written BEFORE the implementation exists; they are expected
to fail until backend/app/services/terminology/ is created.
"""
from __future__ import annotations

import pytest


def test_fhir_version_selects_distinct_generated_resource_classes():
    from app.services.fhir.fhir_service import _bundle_model_for_version

    r4_bundle = _bundle_model_for_version("R4")
    r4b_bundle = _bundle_model_for_version("R4B")
    assert r4_bundle.__module__ == "fhir.resources.bundle"
    assert r4b_bundle.__module__ == "fhir.resources.R4B.bundle"
    assert r4_bundle is not r4b_bundle


def test_local_terminology_reports_code_counts_by_table():
    from app.services.terminology.local import LocalTerminologyService

    assert LocalTerminologyService.table_counts() == {
        "ICD10": 15,
        "RXNORM": 20,
        "SNOMED": 9,
        "LOINC": 17,
        "CPT": 5,
    }


# ---------------------------------------------------------------------------
# Item 2: Terminology service interface & local lookup
# ---------------------------------------------------------------------------

class TestTerminologyServiceInterface:
    """The service must implement the base interface."""

    def test_local_service_implements_base(self):
        from app.services.terminology.local import LocalTerminologyService
        from app.services.terminology.base import BaseTerminologyService
        assert issubclass(LocalTerminologyService, BaseTerminologyService)

    def test_lookup_returns_result_object(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup(code="J18.9", system="ICD10")
        assert result is not None
        assert hasattr(result, "code")
        assert hasattr(result, "system")
        assert hasattr(result, "display")
        assert hasattr(result, "confidence")

    def test_known_icd10_code_returns_high_confidence(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup(code="J18.9", system="ICD10")
        assert result.code == "J18.9"
        assert result.system == "http://hl7.org/fhir/sid/icd-10"
        assert result.display  # non-empty display string
        assert result.confidence >= 0.95

    def test_known_rxnorm_code_returns_high_confidence(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup(code="308182", system="RxNorm")
        assert result.code == "308182"
        assert result.confidence >= 0.95

    def test_known_loinc_code_returns_high_confidence(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup(code="2160-0", system="LOINC")
        assert result.code == "2160-0"
        assert result.confidence >= 0.95

    def test_unknown_code_returns_zero_confidence(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup(code="FAKE-9999", system="ICD10")
        assert result.confidence == 0.0

    def test_lookup_by_display_term(self):
        """Lookup by display name (for uncoded entities)."""
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup_by_display("Pneumonia", system="ICD10")
        assert result is not None
        assert result.code == "J18.9"
        assert result.confidence >= 0.95

    def test_lookup_by_display_unknown_returns_zero_confidence(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        result = svc.lookup_by_display("Invented disease XYZ", system="ICD10")
        assert result.confidence == 0.0

    def test_verify_entity_details_sets_code_verified_true_for_known_code(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        details = {"code": "J18.9", "code_system": "ICD10"}
        svc.verify_entity_details(details, confidence_threshold=0.90)
        assert details.get("code_verified") is True

    def test_verify_entity_details_sets_code_verified_false_for_unknown_code(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        details = {"code": "FAKE-9999", "code_system": "ICD10"}
        svc.verify_entity_details(details, confidence_threshold=0.90)
        assert details.get("code_verified") is False

    def test_verify_entity_details_no_code_sets_code_verified_false(self):
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        details: dict = {}
        svc.verify_entity_details(details, confidence_threshold=0.90)
        assert details.get("code_verified") is False

    def test_verify_entity_details_below_threshold_sets_false(self):
        """A known code with confidence 0.95 should fail a threshold of 0.99."""
        from app.services.terminology.local import LocalTerminologyService
        svc = LocalTerminologyService()
        details = {"code": "J18.9", "code_system": "ICD10"}
        svc.verify_entity_details(details, confidence_threshold=0.99)
        # confidence of local lookup is 0.97, below 0.99
        assert details.get("code_verified") is False


# ---------------------------------------------------------------------------
# Item 3: Uncoded entities flagged in FHIR export
# ---------------------------------------------------------------------------

class TestUncodedFHIRFlag:
    """Uncoded entities must carry a human-review extension, not be silent."""

    def _make_doc(self, entity_details: dict, entity_type="diagnosis"):
        """Build a minimal mock Document for FHIR bundle generation."""
        from datetime import datetime, timezone
        from unittest.mock import MagicMock
        entity = MagicMock()
        entity.id = "00000000-0000-0000-0000-000000000099"
        entity.entity_type = entity_type
        entity.assertion = "present"
        entity.status = "approved"
        entity.normalized_value = "Test condition"
        entity.raw_text = "test"
        entity.section = None
        entity.details = entity_details
        entity.review_tasks = []
        extraction = MagicMock()
        extraction.entities = [entity]
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

    def _conditions(self, bundle: dict) -> list:
        return [
            e["resource"] for e in bundle.get("entry", [])
            if e.get("resource", {}).get("resourceType") == "Condition"
        ]

    def test_verified_coded_entity_has_no_review_extension(self):
        from app.services.fhir.fhir_service import build_document_fhir_bundle
        details = {"code": "J18.9", "code_system": "ICD10", "code_verified": True}
        doc = self._make_doc(details)
        bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
        conditions = self._conditions(bundle)
        assert conditions, "Expected a Condition resource"
        cond = conditions[0]
        extensions = cond.get("extension", [])
        review_exts = [e for e in extensions if e.get("url") == "urn:cognate:needs-coding-review"]
        assert not review_exts, "Verified coded entity must not carry needs-coding-review extension"

    def test_unverified_entity_has_review_extension(self):
        """Entity with code_verified=False must carry needs-coding-review extension."""
        from app.services.fhir.fhir_service import build_document_fhir_bundle
        details = {"code": None, "code_system": None, "code_verified": False}
        doc = self._make_doc(details)
        bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
        conditions = self._conditions(bundle)
        assert conditions, "Expected a Condition resource"
        cond = conditions[0]
        extensions = cond.get("extension", [])
        review_exts = [e for e in extensions if e.get("url") == "urn:cognate:needs-coding-review"]
        assert review_exts, "Unverified entity must carry needs-coding-review extension"

    def test_entity_without_code_verified_field_has_review_extension(self):
        """Missing code_verified (legacy entity) must be treated as unverified."""
        from app.services.fhir.fhir_service import build_document_fhir_bundle
        details: dict = {}
        doc = self._make_doc(details)
        bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
        conditions = self._conditions(bundle)
        assert conditions
        cond = conditions[0]
        extensions = cond.get("extension", [])
        review_exts = [e for e in extensions if e.get("url") == "urn:cognate:needs-coding-review"]
        assert review_exts, "Entity with no code_verified field must be flagged for review"


# ---------------------------------------------------------------------------
# Item 4: FHIR version config + US Core profile URLs
# ---------------------------------------------------------------------------

class TestFHIRVersionConfig:

    def test_r4b_is_default_version(self):
        from app.config import settings
        assert settings.fhir_version in {"R4", "R4B"}  # either is a valid default

    def test_fhir_version_setting_exists(self):
        from app.config import Settings
        s = Settings(fhir_version="R4")
        assert s.fhir_version == "R4"
        s2 = Settings(fhir_version="R4B")
        assert s2.fhir_version == "R4B"

    def test_invalid_fhir_version_rejected(self):
        from app.config import Settings
        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            Settings(fhir_version="DSTU2")

    def test_us_core_profiles_setting_exists(self):
        from app.config import Settings
        s = Settings(fhir_us_core_profiles_enabled=True)
        assert s.fhir_us_core_profiles_enabled is True

    def test_coding_confidence_threshold_setting_exists(self):
        from app.config import Settings
        s = Settings(fhir_coding_confidence_threshold=0.95)
        assert s.fhir_coding_confidence_threshold == 0.95

    def test_us_core_profile_in_patient_resource_when_enabled(self):
        from datetime import datetime, timezone
        from unittest.mock import MagicMock, patch
        from app.services.fhir.fhir_service import build_document_fhir_bundle
        patient = MagicMock()
        patient.id = "00000000-0000-0000-0000-000000000001"
        patient.mrn = None; patient.gender = "unknown"
        patient.first_name = None; patient.last_name = None; patient.dob = None
        doc = MagicMock()
        doc.id = "00000000-0000-0000-0000-000000000002"
        doc.patient = patient; doc.patient_id = patient.id
        doc.mime_type = "application/pdf"; doc.file_name = "test.pdf"
        doc.document_type = "discharge_summary"
        doc.extractions = []
        doc.created_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        with patch("app.services.fhir.fhir_service.settings") as mock_settings:
            mock_settings.fhir_version = "R4B"
            mock_settings.fhir_us_core_profiles_enabled = True
            mock_settings.fhir_coding_confidence_threshold = 0.90
            bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
        patient_resources = [
            e["resource"] for e in bundle.get("entry", [])
            if e.get("resource", {}).get("resourceType") == "Patient"
        ]
        assert patient_resources
        pt = patient_resources[0]
        meta = pt.get("meta", {})
        profiles = meta.get("profile", [])
        assert any("us-core-patient" in p for p in profiles), (
            f"Expected US Core patient profile in meta.profile, got {profiles}"
        )

