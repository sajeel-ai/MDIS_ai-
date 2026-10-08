"""Unit tests for MIMIC-IV-Note ingestion service and provenance verification."""

import hashlib
from pathlib import Path

import pytest
from app.db import AsyncSessionLocal
from app.models import Document, DocumentVersion, Patient
from app.services.documents.mimic_note_service import (
    ingest_mimic_notes_from_file,
    map_note_type,
    read_csv_records,
    validate_source_files,
)
from sqlalchemy import select


def test_map_note_type():
    assert map_note_type("DS", "discharge.csv") == "discharge_summary"
    assert map_note_type("RR", "radiology.csv") == "radiology_report"
    assert map_note_type(None, "discharge_notes.csv") == "discharge_summary"
    assert map_note_type(None, "other.csv") == "clinical_note"


def test_validate_source_files(tmp_path):
    (tmp_path / "discharge.csv").write_text("note_id,text\n1,test")
    files = validate_source_files(tmp_path)
    assert len(files) == 1
    assert files[0].name == "discharge.csv"


def test_read_csv_records(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("note_id,subject_id,text\nN1,1001,Clinical note content")
    records = list(read_csv_records(csv_file))
    assert len(records) == 1
    assert records[0]["note_id"] == "N1"
    assert records[0]["subject_id"] == "1001"
    assert records[0]["text"] == "Clinical note content"


@pytest.mark.asyncio
async def test_ingest_mimic_notes_idempotency_and_hash(tmp_path):
    import uuid
    from app.db import engine
    await engine.dispose()
    async with AsyncSessionLocal() as session:
        test_id = f"NOTE-TEST-{uuid.uuid4().hex[:8]}"
        storage_key = f"mimic-notes/{test_id}.txt"
        csv_file = tmp_path / "discharge.csv"
        note_text = "Admission Date: 2026-09-24 Discharge Summary text content."
        csv_file.write_text(
            f"note_id,subject_id,hadm_id,note_type,text\n{test_id},999001,888001,DS,\"{note_text}\"\n"
        )

        # 1st Ingestion
        stats1 = await ingest_mimic_notes_from_file(
            file_path=csv_file,
            session=session,
            run_pipeline=False,
        )
        assert stats1["inserted_documents"] == 1
        assert stats1["hash_verified"] == 1

        # Verify Document & Version in DB
        res = await session.execute(
            select(Document).where(Document.storage_key == storage_key)
        )
        doc = res.scalars().first()
        assert doc is not None
        assert doc.source == "MIMIC-IV-Note"

        ver_res = await session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
        )
        ver = ver_res.scalars().first()
        assert ver is not None
        expected_hash = hashlib.sha256(note_text.encode("utf-8")).hexdigest()
        assert ver.text_hash == expected_hash

        # 2nd Ingestion (Idempotent test - should skip existing)
        stats2 = await ingest_mimic_notes_from_file(
            file_path=csv_file,
            session=session,
            run_pipeline=False,
        )
        assert stats2["inserted_documents"] == 0
        assert stats2["existing_documents"] == 1
