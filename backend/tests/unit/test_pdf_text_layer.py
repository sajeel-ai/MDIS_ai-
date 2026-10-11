"""Regression tests for Unicode-preserving digital PDF extraction."""

from pathlib import Path

import pytest

from app.providers.ocr.local import LocalOCRProvider


@pytest.fixture
def tmp_path():
    return Path.cwd()


@pytest.mark.asyncio
async def test_digital_pdf_uses_text_layer_and_preserves_units_and_unicode():
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(
        (50, 80),
        "Lab\tResult\tReference\tFlag\nWBC\t4.2 x10^9/L\t4.0-11.0\tNormal\nHemoglobin\t13 g/dL\t12-16\tNormal\nPatient: Zo\u00eb \u00b5g \u00b7 37\u00b0C",
    )
    pdf_bytes = pdf.tobytes()
    pdf.close()

    result = await LocalOCRProvider().extract_text(pdf_bytes, "application/pdf")

    assert result["engine"] == "pymupdf_text_layer"
    assert result["pages"][0]["method"] == "text_layer"
    assert "x10^9/L" in result["text"]
    assert "g/dL" in result["text"]
    assert "Zo\u00eb \u00b5g \u00b7 37\u00b0C" in result["text"]
    assert "4.0-11.0" in result["text"]


@pytest.mark.asyncio
async def test_utf8_text_round_trips_without_redecoding():
    text = "Patient Zo\u00eb \u00b7 dose 5 \u00b5g \u00b7 threshold \u2265 37\u00b0C"
    result = await LocalOCRProvider().extract_text(text.encode("utf-8"), "text/plain")
    assert result["text"] == text

