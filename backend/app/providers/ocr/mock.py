"""Mock OCR Provider for offline/fast testing."""

from app.providers.ocr.base import BaseOCRProvider, OCRResult


class MockOCRProvider(BaseOCRProvider):
    async def extract_text(self, file_bytes: bytes, mime_type: str | None = None) -> OCRResult:
        decoded = ""
        try:
            decoded = file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            decoded = "MOCK CLINICAL NOTE\nPatient presented with fever and cough."

        if not decoded.strip():
            decoded = (
                "CLINICAL PROGRESS NOTE\n"
                "Patient presented with dyspnea and persistent fever (38.5 C).\n"
                "Diagnosis: Community-acquired pneumonia.\n"
                "Medication: Amoxicillin 500 mg PO TID."
            )

        return OCRResult(
            text=decoded,
            confidence=None,
            page_count=1,
            engine="mock_ocr",
        )
