"""Unit tests for LocalOCRProvider (Tesseract & pdftoppm) and clinical processing pipeline integration."""

from pathlib import Path

import pytest
from app.db import AsyncSessionLocal, engine
from app.models import Document, Patient, ProcessingJob
from app.config import settings
from app.providers.ocr.local import LocalOCRProvider
from app.providers.storage import get_storage_provider
from app.workflows.clinical_processing import ClinicalProcessingWorkflow
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select


@pytest.fixture
def local_ocr():
    return LocalOCRProvider()


@pytest.mark.asyncio
async def test_ocr_text_file(local_ocr):
    content = b"DISCHARGE SUMMARY\nPatient: John Doe\nDiagnosis: Hypertension"
    res = await local_ocr.extract_text(content, mime_type="text/plain")
    assert "DISCHARGE SUMMARY" in res["text"]
    assert res["page_count"] == 1
    assert res["confidence"] is None


@pytest.mark.asyncio
async def test_ocr_medical_image(local_ocr, tmp_path):
    # Create synthetic medical note PNG image using PIL
    im = Image.new("RGB", (600, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.text((20, 20), "CLINICAL PROGRESS NOTE", fill=(0, 0, 0))
    draw.text((20, 50), "Diagnosis: Acute Bronchitis", fill=(0, 0, 0))
    draw.text((20, 80), "Rx: Azithromycin 250mg PO", fill=(0, 0, 0))

    image_path = tmp_path / "medical-note.png"
    im.save(image_path)
    res = await local_ocr.extract_text(image_path.read_bytes(), mime_type="image/png")
    assert "CLINICAL" in res["text"] or "PROGRESS" in res["text"]
    assert res["page_count"] == 1
    assert res["engine"] == "tesseract_local"
    assert res["confidence"] is not None
    assert 0 <= res["confidence"] <= 1
    assert res["pages"][0]["confidence"] == res["confidence"]


def test_image_ocr_confidence_averages_word_confidence_and_ignores_minus_one(monkeypatch, tmp_path):
    import pytesseract
    import app.providers.ocr.local as local_ocr_module

    image_path = tmp_path / "confidence.png"
    Image.new("RGB", (8, 8), color=(255, 255, 255)).save(image_path)
    monkeypatch.setattr(local_ocr_module, "_tesseract_executable", lambda: "tesseract")
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {"text": ["word", "", "word"], "conf": ["80", "-1", "60"]},
    )
    text, confidence = local_ocr_module.LocalOCRProvider._tesseract_image_data(str(image_path))
    assert text == "word word"
    assert confidence == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_ocr_scanned_pdf(local_ocr, tmp_path):
    # Create scanned PDF by converting an image to PDF via PIL
    im = Image.new("RGB", (600, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.text((20, 20), "RADIOLOGY REPORT", fill=(0, 0, 0))
    draw.text((20, 50), "Impression: No acute cardiopulmonary abnormality", fill=(0, 0, 0))

    pdf_path = tmp_path / "scanned-note.pdf"
    im.save(pdf_path, "PDF", resolution=100.0)
    res = await local_ocr.extract_text(pdf_path.read_bytes(), mime_type="application/pdf")
    assert "RADIOLOGY" in res["text"] or "REPORT" in res["text"] or "Impression" in res["text"]
    assert res["page_count"] >= 1
    assert res["confidence"] is None or 0 <= res["confidence"] <= 1


@pytest.mark.asyncio
async def test_clinical_processing_hard_failures(monkeypatch):
    monkeypatch.setattr(settings, "extraction_provider", "mock")
    await engine.dispose()
    async with AsyncSessionLocal() as session:
        # Create test patient & doc without storage key
        pat = Patient(external_patient_id="TEST-OCR-PAT", gender="F")
        session.add(pat)
        await session.flush()

        doc = Document(
            patient_id=pat.id,
            document_type="discharge_summary",
            source="Test",
            file_name="test.txt",
            mime_type="text/plain",
            size_bytes=0,
            storage_key=None,  # Missing storage key
            status="uploaded",
        )
        session.add(doc)
        await session.flush()

        job = ProcessingJob(document_id=doc.id, pipeline_version="v1.4.2", status="queued")
        session.add(job)
        await session.commit()

        workflow = ClinicalProcessingWorkflow(session)
        with pytest.raises(RuntimeError, match="PROCESSING_INPUT_MISSING"):
            await workflow.execute_job(job.id)


@pytest.mark.asyncio
async def test_clinical_processing_pipeline_with_real_local_ocr(monkeypatch):
    monkeypatch.setattr(settings, "extraction_provider", "mock")
    await engine.dispose()
    async with AsyncSessionLocal() as session:
        storage = get_storage_provider()
        note_text = (
            "CLINICAL NOTE\n"
            "Patient presented with dyspnea and fever.\n"
            "Diagnosis: Acute exacerbation of COPD.\n"
            "Medication: Prednisone 40 mg PO daily for 5 days."
        )
        storage_key = "documents/test_real_ocr.txt"
        await storage.save_file(storage_key, note_text.encode("utf-8"))

        pat = Patient(external_patient_id="PAT-REAL-OCR-1", gender="M")
        session.add(pat)
        await session.flush()

        doc = Document(
            patient_id=pat.id,
            document_type="discharge_summary",
            source="TestLocalOCR",
            file_name="test_real_ocr.txt",
            mime_type="text/plain",
            size_bytes=len(note_text),
            storage_key=storage_key,
            status="uploaded",
        )
        session.add(doc)
        await session.flush()

        job = ProcessingJob(document_id=doc.id, pipeline_version="v1.4.2", status="queued")
        session.add(job)
        await session.commit()

        workflow = ClinicalProcessingWorkflow(session)
        completed_job = await workflow.execute_job(job.id)

        assert completed_job.status == "completed"
        assert doc.status == "completed"
