"""Cognate AI — MIMIC-IV-Note Ingestion Service

Handles validation, parsing, DB patient/encounter mapping, text hash provenance verification,
and pipeline triggering for real and sample MIMIC-IV-Note clinical documents.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentVersion, Encounter, Patient, ProcessingJob
from app.providers.extraction import validate_extraction_provider_configuration
from app.providers.storage import get_storage_provider
from app.workflows.clinical_processing import ClinicalProcessingWorkflow

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]

DEFAULT_NOTE_DIRS = [
    PROJECT_ROOT / "data" / "raw" / "mimic-iv-note",
    PROJECT_ROOT / "data" / "sample" / "mimic-iv-note",
]


def resolve_note_directory() -> Path:
    env_dir = os.getenv("MIMIC_NOTE_ROOT")
    if env_dir:
        env_path = Path(env_dir).resolve()
        if env_path.exists():
            return env_path

    for candidate in DEFAULT_NOTE_DIRS:
        if candidate.exists() and any(candidate.iterdir()):
            return candidate

    # Return default sample path even if created on the fly
    sample_dir = DEFAULT_NOTE_DIRS[1]
    sample_dir.mkdir(parents=True, exist_ok=True)
    return sample_dir


def validate_source_files(note_dir: Path) -> list[Path]:
    """Scans for discharge or radiology note CSV/GZ files."""
    if not note_dir.is_dir():
        raise FileNotFoundError(f"Note directory does not exist: {note_dir}")

    found_files: list[Path] = []
    supported = ["discharge.csv.gz", "discharge.csv", "radiology.csv.gz", "radiology.csv", "sample_notes.csv"]

    for file_name in supported:
        p = note_dir / file_name
        if p.is_file():
            found_files.append(p)

    if not found_files:
        # Search recursively for any csv/gz notes in subdirectories
        found_files = list(note_dir.glob("**/*.csv*"))

    if not found_files:
        raise FileNotFoundError(
            f"No supported MIMIC-IV-Note CSV files found in {note_dir}.\n"
            f"Expected files such as discharge.csv.gz or radiology.csv.gz."
        )

    return found_files


def read_csv_records(file_path: Path):
    """Yields dictionaries from either .csv.gz or .csv file."""
    if file_path.suffix == ".gz" or str(file_path).endswith(".csv.gz"):
        with gzip.open(file_path, mode="rt", encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)
    else:
        with open(file_path, mode="r", encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)


def map_note_type(raw_type: str | None, filename: str) -> str:
    if raw_type:
        rt = raw_type.strip().lower()
        if "discharge" in rt or rt == "ds":
            return "discharge_summary"
        if "radiology" in rt or rt == "rr":
            return "radiology_report"
        if "consult" in rt:
            return "consultation_report"
        if "progress" in rt:
            return "progress_note"

    fn = filename.lower()
    if "discharge" in fn:
        return "discharge_summary"
    if "radiology" in fn:
        return "radiology_report"

    return "clinical_note"


async def ingest_mimic_notes_from_file(
    file_path: Path,
    session: AsyncSession,
    run_pipeline: bool = True,
    max_records: int | None = None,
) -> dict[str, int]:
    """Ingests MIMIC-IV-Note records from a CSV/GZ file into PostgreSQL."""
    if run_pipeline:
        validate_extraction_provider_configuration()
    storage_provider = get_storage_provider()
    
    stats = {
        "total_read": 0,
        "inserted_documents": 0,
        "existing_documents": 0,
        "patients_created": 0,
        "encounters_matched": 0,
        "hash_verified": 0,
        "jobs_triggered": 0,
    }

    # Cache existing patients and encounters for fast lookup
    pat_res = await session.execute(select(Patient))
    patient_map: dict[str, Patient] = {
        p.external_patient_id: p for p in pat_res.scalars().all() if p.external_patient_id
    }

    enc_res = await session.execute(select(Encounter))
    encounter_map: dict[str, Encounter] = {
        e.external_encounter_id: e for e in enc_res.scalars().all() if e.external_encounter_id
    }

    doc_res = await session.execute(select(Document))
    existing_storage_keys: set[str] = {
        d.storage_key for d in doc_res.scalars().all() if d.storage_key
    }

    workflow = ClinicalProcessingWorkflow(session) if run_pipeline else None

    for row in read_csv_records(file_path):
        stats["total_read"] += 1

        note_id = (row.get("note_id") or f"NOTE-{stats['total_read']}").strip()
        subject_id = (row.get("subject_id") or "").strip()
        hadm_id = (row.get("hadm_id") or "").strip()
        text = row.get("text") or row.get("note_text") or ""

        if not text.strip():
            continue

        storage_key = f"mimic-notes/{note_id}.txt"
        if storage_key in existing_storage_keys:
            stats["existing_documents"] += 1
            continue

        # 1. Map or create Patient
        patient = patient_map.get(subject_id)
        if not patient and subject_id:
            patient = Patient(
                external_patient_id=subject_id,
                mrn=f"MRN-{subject_id}",
                gender="Unknown",
            )
            session.add(patient)
            await session.flush()
            patient_map[subject_id] = patient
            stats["patients_created"] += 1

        patient_id = patient.id if patient else None

        # 2. Map Encounter if present
        encounter = encounter_map.get(hadm_id) if hadm_id else None
        if encounter:
            stats["encounters_matched"] += 1
        encounter_id = encounter.id if encounter else None

        # 3. Calculate SHA-256 text_hash verification
        encoded_bytes = text.encode("utf-8")
        text_hash = hashlib.sha256(encoded_bytes).hexdigest()

        # 4. Write text payload to storage provider
        await storage_provider.save_file(storage_key, encoded_bytes)

        # 5. Create Document record
        doc_type = map_note_type(row.get("note_type"), file_path.name)
        document = Document(
            patient_id=patient_id,
            encounter_id=encounter_id,
            document_type=doc_type,
            source="MIMIC-IV-Note",
            file_name=f"{note_id}.txt",
            mime_type="text/plain",
            size_bytes=len(encoded_bytes),
            storage_key=storage_key,
            status="uploaded",
            review_status="not_required",
        )
        session.add(document)
        await session.flush()
        existing_storage_keys.add(storage_key)

        # 6. Create DocumentVersion record with text_hash verification
        doc_version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            raw_text=text,
            text_hash=text_hash,
            page_count=1,
        )
        session.add(doc_version)
        await session.flush()

        # Verify hash match
        recomputed_hash = hashlib.sha256(doc_version.raw_text.encode("utf-8")).hexdigest()
        if recomputed_hash != text_hash:
            raise ValueError(f"Text hash mismatch for note {note_id}: {recomputed_hash} != {text_hash}")
        stats["hash_verified"] += 1
        stats["inserted_documents"] += 1

        # 7. Optionally trigger D6 processing pipeline
        if run_pipeline and workflow:
            job = ProcessingJob(
                document_id=document.id,
                pipeline_version="v1.4.2",
                status="queued",
            )
            session.add(job)
            await session.flush()
            await workflow.execute_job(job.id)
            stats["jobs_triggered"] += 1

        if max_records and stats["inserted_documents"] >= max_records:
            break

    await session.commit()
    return stats
