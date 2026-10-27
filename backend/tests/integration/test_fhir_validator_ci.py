"""CI test: run the HL7 FHIR validator on a generated bundle — Item 5.

This test is skipped unless:
  - FHIR_VALIDATOR_JAR env var points to the validator JAR
  - java is on PATH

To run locally:
  set FHIR_VALIDATOR_JAR=C:\\path\\to\\validator_cli.jar
  pytest tests/integration/test_fhir_validator_ci.py -v

In CI, add a step to download the validator:
  curl -fsSL https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar -o validator_cli.jar
  set FHIR_VALIDATOR_JAR=validator_cli.jar
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

VALIDATOR_JAR = os.environ.get("FHIR_VALIDATOR_JAR", "")
JAVA = shutil.which("java")

pytestmark = pytest.mark.skipif(
    not VALIDATOR_JAR or not JAVA,
    reason="FHIR_VALIDATOR_JAR env var and java must both be available",
)


def _minimal_doc(entity_details: dict | None = None) -> MagicMock:
    """Build a minimal Document mock suitable for FHIR export."""
    patient = MagicMock()
    patient.id = "00000000-0000-0000-0000-000000000001"
    patient.mrn = "MRN001"
    patient.gender = "female"
    patient.first_name = "Jane"
    patient.last_name = "Doe"
    patient.dob = None

    entities = []
    if entity_details is not None:
        entity = MagicMock()
        entity.id = "00000000-0000-0000-0000-000000000099"
        entity.entity_type = "diagnosis"
        entity.assertion = "present"
        entity.status = "approved"
        entity.normalized_value = "Pneumonia"
        entity.raw_text = "pneumonia"
        entity.section = None
        entity.details = entity_details
        entity.review_tasks = []
        entities = [entity]

    extraction = MagicMock()
    extraction.entities = entities
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


def _run_validator(bundle_json: str, fhir_version: str = "4.3.0") -> subprocess.CompletedProcess:
    """Write bundle to a temp file and run the HL7 FHIR validator on it."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(bundle_json)
        tmp_path = f.name
    try:
        return subprocess.run(
            [JAVA, "-jar", VALIDATOR_JAR, tmp_path, "-version", fhir_version, "-output", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        os.unlink(tmp_path)


def _error_count(result: subprocess.CompletedProcess) -> int:
    """Parse error count from validator stdout/stderr."""
    combined = (result.stdout or "") + (result.stderr or "")
    # The validator outputs "Error" lines when there are validation failures
    errors = [line for line in combined.splitlines() if "error" in line.lower() and "0 error" not in line.lower()]
    return len(errors)


@pytest.mark.integration
def test_empty_bundle_passes_validator():
    """A bundle with no clinical entities must pass the FHIR validator."""
    from app.services.fhir.fhir_service import build_document_fhir_bundle
    doc = _minimal_doc(entity_details=None)
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    result = _run_validator(json.dumps(bundle))
    errors = _error_count(result)
    assert errors == 0, (
        f"FHIR validator reported {errors} error(s):\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


@pytest.mark.integration
def test_bundle_with_coded_condition_passes_validator():
    """A bundle with a verified ICD-10 Condition must pass the FHIR validator."""
    from app.services.fhir.fhir_service import build_document_fhir_bundle
    details = {
        "code": "J18.9",
        "code_system": "ICD10",
        "code_verified": True,
        "display": "Pneumonia, unspecified",
    }
    doc = _minimal_doc(entity_details=details)
    bundle = build_document_fhir_bundle(doc, include_unreviewed=True)
    result = _run_validator(json.dumps(bundle))
    errors = _error_count(result)
    assert errors == 0, (
        f"FHIR validator reported {errors} error(s):\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

