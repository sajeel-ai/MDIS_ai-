"""Cognate AI — MIMIC-IV-Note Ingestion CLI Script.

Imports MIMIC-IV-Note clinical text documents, validates file integrity,
maps subject_id -> patient and hadm_id -> encounter in PostgreSQL, verifies SHA-256 text_hash,
and executes the D6 clinical document processing pipeline.

Usage:
    cd backend
    python3 -m scripts.ingest_mimic_notes
    python3 -m scripts.ingest_mimic_notes --max 10
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.db import AsyncSessionLocal
from app.services.documents.mimic_note_service import (
    ingest_mimic_notes_from_file,
    resolve_note_directory,
    validate_source_files,
)


async def main():
    parser = argparse.ArgumentParser(description="Ingest MIMIC-IV-Note clinical text notes.")
    parser.add_argument("--dir", type=str, help="Path to MIMIC-IV-Note root directory.")
    parser.add_argument("--file", type=str, help="Path to a specific note CSV or CSV.GZ file.")
    parser.add_argument("--max", type=int, default=None, help="Maximum number of note records to ingest.")
    parser.add_argument("--no-pipeline", action="store_true", help="Skip running the D6 processing pipeline.")
    args = parser.parse_args()

    print("=" * 70)
    print("MIMIC-IV-NOTE INGESTION PIPELINE")
    print("=" * 70)

    if args.file:
        file_paths = [Path(args.file).resolve()]
        if not file_paths[0].is_file():
            print(f"ERROR: Specified file does not exist: {file_paths[0]}")
            sys.exit(1)
    else:
        note_dir = Path(args.dir).resolve() if args.dir else resolve_note_directory()
        print(f"Target note directory: {note_dir}")
        try:
            file_paths = validate_source_files(note_dir)
        except FileNotFoundError as err:
            print(f"VALIDATION FAILED: {err}")
            sys.exit(1)

    print(f"Files to process ({len(file_paths)}):")
    for fp in file_paths:
        print(f"  • {fp}")
    print()

    run_pipeline = not args.no_pipeline

    async with AsyncSessionLocal() as session:
        for fp in file_paths:
            print(f"=== Processing {fp.name} ===")
            stats = await ingest_mimic_notes_from_file(
                file_path=fp,
                session=session,
                run_pipeline=run_pipeline,
                max_records=args.max,
            )
            print("  Total read:          ", stats["total_read"])
            print("  Inserted documents:  ", stats["inserted_documents"])
            print("  Existing skipped:    ", stats["existing_documents"])
            print("  Patients created:    ", stats["patients_created"])
            print("  Encounters matched:  ", stats["encounters_matched"])
            print("  SHA-256 verified:    ", stats["hash_verified"])
            print("  Pipeline jobs run:   ", stats["jobs_triggered"])
            print()

    print("=" * 70)
    print("MIMIC-IV-NOTE INGESTION & PIPELINE VERIFICATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
