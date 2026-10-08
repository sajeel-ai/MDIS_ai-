"""Cognate AI — MIMIC-IV Demo relational ingestion.

Imports real MIMIC-IV Demo v2.2 structured data:

    patients.csv.gz
        -> patients

    admissions.csv.gz
        -> encounters

    diagnoses_icd.csv.gz
    d_icd_diagnoses.csv.gz
        -> icd_codes

This script intentionally does NOT create Document or DocumentVersion
records because MIMIC-IV Demo does not contain free-text clinical notes.

The ingestion is idempotent and has NO synthetic-data fallback.

Usage:
    cd backend
    PYTHONPATH=. python3 -m scripts.ingest_mimic
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Encounter, IcdCode, Patient


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MIMIC_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "mimic-iv-demo"
    / "physionet.org"
    / "files"
    / "mimic-iv-demo"
    / "2.2"
)

MIMIC_ROOT = Path(
    os.getenv("MIMIC_DEMO_ROOT", str(DEFAULT_MIMIC_ROOT))
).resolve()

HOSP_DIR = MIMIC_ROOT / "hosp"


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def required_file(filename: str) -> Path:
    path = HOSP_DIR / filename

    if not path.is_file():
        raise FileNotFoundError(
            f"Required MIMIC file not found:\n{path}"
        )

    return path


def read_gzip_csv(path: Path):
    with gzip.open(
        path,
        mode="rt",
        encoding="utf-8",
        newline="",
    ) as file:
        yield from csv.DictReader(file)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    return datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    )


def calculate_los_hours(
    admit_time: datetime | None,
    discharge_time: datetime | None,
) -> Decimal | None:

    if not admit_time or not discharge_time:
        return None

    seconds = (
        discharge_time - admit_time
    ).total_seconds()

    if seconds < 0:
        raise ValueError(
            "Invalid MIMIC admission: discharge time occurs "
            f"before admission time "
            f"({admit_time} -> {discharge_time})"
        )

    return Decimal(
        str(round(seconds / 3600, 2))
    )


def normalize_gender(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip().upper()

    if value in {"M", "F"}:
        return value

    return "Unknown"


# ---------------------------------------------------------------------------
# Dataset validation
# ---------------------------------------------------------------------------

def validate_dataset() -> dict[str, Path]:

    files = {
        "patients": required_file("patients.csv.gz"),
        "admissions": required_file("admissions.csv.gz"),
        "diagnoses": required_file("diagnoses_icd.csv.gz"),
        "diagnosis_dictionary": required_file(
            "d_icd_diagnoses.csv.gz"
        ),
    }

    print("=" * 70)
    print("MIMIC-IV DATASET VALIDATION")
    print("=" * 70)
    print(f"MIMIC root: {MIMIC_ROOT}")

    for name, path in files.items():
        print(f"{name:<24}: {path}")

    print()

    return files


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

async def ingest_patients(
    patients_file: Path,
    session,
) -> dict[str, Patient]:

    print("=== PATIENTS ===")

    result = await session.execute(
        select(Patient)
    )

    existing_patients = result.scalars().all()

    patient_map: dict[str, Patient] = {
        patient.external_patient_id: patient
        for patient in existing_patients
        if patient.external_patient_id
    }

    inserted = 0
    existing = 0

    for row in read_gzip_csv(patients_file):

        subject_id = (
            row.get("subject_id") or ""
        ).strip()

        if not subject_id:
            raise ValueError(
                "patients.csv.gz contains a row without subject_id"
            )

        patient = patient_map.get(subject_id)

        if patient:
            existing += 1
            continue

        patient = Patient(
            external_patient_id=subject_id,
            mrn=None,
            first_name=None,
            last_name=None,
            dob=None,
            gender=normalize_gender(
                row.get("gender")
            ),
        )

        session.add(patient)

        patient_map[subject_id] = patient
        inserted += 1

    await session.flush()

    print(f"Inserted: {inserted}")
    print(f"Existing: {existing}")
    print(f"Total:    {len(patient_map)}")
    print()

    return patient_map


# ---------------------------------------------------------------------------
# Encounters
# ---------------------------------------------------------------------------

async def ingest_encounters(
    admissions_file: Path,
    patient_map: dict[str, Patient],
    session,
) -> dict[str, Encounter]:

    print("=== ENCOUNTERS ===")

    result = await session.execute(
        select(Encounter)
    )

    existing_encounters = result.scalars().all()

    encounter_map: dict[str, Encounter] = {
        encounter.external_encounter_id: encounter
        for encounter in existing_encounters
        if encounter.external_encounter_id
    }

    inserted = 0
    existing = 0
    orphan_patients = 0

    for row in read_gzip_csv(admissions_file):

        subject_id = (
            row.get("subject_id") or ""
        ).strip()

        hadm_id = (
            row.get("hadm_id") or ""
        ).strip()

        if not subject_id or not hadm_id:
            raise ValueError(
                "admissions.csv.gz contains a row without "
                "subject_id or hadm_id"
            )

        patient = patient_map.get(subject_id)

        if patient is None:
            orphan_patients += 1
            continue

        encounter = encounter_map.get(hadm_id)

        if encounter:
            existing += 1
            continue

        admit_time = parse_datetime(
            row.get("admittime")
        )

        discharge_time = parse_datetime(
            row.get("dischtime")
        )

        encounter = Encounter(
            patient_id=patient.id,
            external_encounter_id=hadm_id,
            admit_time=admit_time,
            discharge_time=discharge_time,
            los_hours=calculate_los_hours(
                admit_time,
                discharge_time,
            ),
        )

        session.add(encounter)

        encounter_map[hadm_id] = encounter
        inserted += 1

    await session.flush()

    print(f"Inserted:           {inserted}")
    print(f"Existing:           {existing}")
    print(f"Orphan patients:    {orphan_patients}")
    print(f"Total:              {len(encounter_map)}")
    print()

    return encounter_map


# ---------------------------------------------------------------------------
# ICD dictionary
# ---------------------------------------------------------------------------

def load_icd_dictionary(
    dictionary_file: Path,
) -> dict[tuple[str, str], str]:

    print("=== ICD DICTIONARY ===")

    dictionary: dict[tuple[str, str], str] = {}

    for row in read_gzip_csv(dictionary_file):

        code = (
            row.get("icd_code") or ""
        ).strip()

        version = (
            row.get("icd_version") or ""
        ).strip()

        description = (
            row.get("long_title")
            or row.get("short_title")
            or ""
        ).strip()

        if code and version:
            dictionary[(code, version)] = description

    print(f"Dictionary entries: {len(dictionary)}")
    print()

    return dictionary


# ---------------------------------------------------------------------------
# ICD diagnoses
# ---------------------------------------------------------------------------

async def ingest_diagnoses(
    diagnoses_file: Path,
    encounter_map: dict[str, Encounter],
    icd_dictionary: dict[tuple[str, str], str],
    session,
) -> None:

    print("=== ICD DIAGNOSES ===")

    result = await session.execute(
        select(IcdCode)
    )

    existing_codes = result.scalars().all()

    existing_keys = {
        (
            code.encounter_id,
            code.code,
            code.code_type,
        )
        for code in existing_codes
    }

    inserted = 0
    existing = 0
    orphan_encounters = 0

    for row in read_gzip_csv(diagnoses_file):

        hadm_id = (
            row.get("hadm_id") or ""
        ).strip()

        icd_code = (
            row.get("icd_code") or ""
        ).strip()

        icd_version = (
            row.get("icd_version") or ""
        ).strip()

        seq_num_raw = (
            row.get("seq_num") or ""
        ).strip()

        if not hadm_id or not icd_code:
            continue

        encounter = encounter_map.get(hadm_id)

        if encounter is None:
            orphan_encounters += 1
            continue

        if icd_version == "9":
            code_type = "ICD-9"
        elif icd_version == "10":
            code_type = "ICD-10"
        else:
            code_type = f"ICD-{icd_version}"

        key = (
            encounter.id,
            icd_code,
            code_type,
        )

        if key in existing_keys:
            existing += 1
            continue

        description = icd_dictionary.get(
            (icd_code, icd_version)
        )

        try:
            seq_num = int(seq_num_raw)
        except ValueError:
            seq_num = None

        is_primary = seq_num == 1

        icd = IcdCode(
            encounter_id=encounter.id,
            code=icd_code,
            description=description,
            code_type=code_type,
            is_primary=is_primary,
        )

        session.add(icd)

        existing_keys.add(key)
        inserted += 1

    await session.flush()

    print(f"Inserted:           {inserted}")
    print(f"Existing:           {existing}")
    print(f"Orphan encounters:  {orphan_encounters}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def ingest_mimic_demo() -> None:

    files = validate_dataset()

    async with AsyncSessionLocal() as session:

        try:

            patient_map = await ingest_patients(
                files["patients"],
                session,
            )

            encounter_map = await ingest_encounters(
                files["admissions"],
                patient_map,
                session,
            )

            icd_dictionary = load_icd_dictionary(
                files["diagnosis_dictionary"]
            )

            await ingest_diagnoses(
                files["diagnoses"],
                encounter_map,
                icd_dictionary,
                session,
            )

            await session.commit()

        except Exception:

            await session.rollback()

            print()
            print("ERROR: ingestion rolled back.")
            raise

    print("=" * 70)
    print("MIMIC-IV DEMO INGESTION COMPLETE")
    print("=" * 70)
    print()
    print("Real MIMIC data was used.")
    print("No synthetic fallback was used.")
    print("No fake DOB values were generated.")
    print("No fake clinical documents were created.")
    print()


if __name__ == "__main__":
    asyncio.run(
        ingest_mimic_demo()
    )
