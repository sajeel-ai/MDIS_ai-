"""Generate synthetic bundles and validate them against official base FHIR R4."""

import argparse
import json
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.services.fhir.fhir_service import build_document_fhir_bundle


def synthetic_document(index: int):
    patient = SimpleNamespace(id=uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-patient-{index}"), gender=("female", "male", "other", "unknown")[index % 4], mrn=None, first_name=None, last_name=None, dob=None)
    entity_types = ("diagnosis", "medication", "lab_result", "procedure", "medication")
    kind = entity_types[index % len(entity_types)]
    section = "ALLERGIES" if index % 5 == 4 else "CLINICAL"
    entity = SimpleNamespace(id=uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-entity-{index}"), entity_type=kind, status="approved", assertion="present", section=section, details={"value": "7.2", "unit": "mmol/L"} if kind == "lab_result" else {}, normalized_value=f"Synthetic {kind}", raw_text=f"Synthetic {kind}", review_tasks=[])
    return SimpleNamespace(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-document-{index}"), patient=patient,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc), updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        mime_type="application/pdf", file_name=f"synthetic-{index}.pdf", document_type="progress_note",
        extractions=[SimpleNamespace(entities=[entity])],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator", required=True, help="Path to official HL7 validator_cli.jar")
    args = parser.parse_args()
    validator = Path(args.validator).resolve()
    if not validator.is_file():
        raise SystemExit("HL7 validator_cli.jar was not found")
    with tempfile.TemporaryDirectory(prefix="cognate-fhir-synthetic-") as temp_dir:
        for index in range(10):
            path = Path(temp_dir) / f"synthetic-{index}.json"
            bundle = build_document_fhir_bundle(synthetic_document(index))
            path.write_text(json.dumps(bundle), encoding="utf-8")
            result = subprocess.run(
                ["java", "-jar", str(validator), str(path), "-version", "4.0.1"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                print(result.stdout)
                print(result.stderr)
                raise SystemExit(f"FHIR R4 validation failed for synthetic fixture {index}")
    print("Official HL7 validator accepted all 10 synthetic FHIR R4 bundles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
