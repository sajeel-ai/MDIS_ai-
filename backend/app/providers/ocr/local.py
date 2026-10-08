"""Local OCR Provider using Tesseract 5 and pdftoppm for PDFs and Images."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.providers.ocr.base import BaseOCRProvider, OCRResult

logger = logging.getLogger(__name__)


def _tesseract_executable() -> str:
    executable = shutil.which("tesseract")
    if executable:
        return executable

    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        installed_executable = program_files / "Tesseract-OCR" / "tesseract.exe"
        if installed_executable.is_file():
            return str(installed_executable)

    raise FileNotFoundError("Tesseract OCR executable is not installed or is missing from PATH")


class LocalOCRProvider(BaseOCRProvider):
    async def extract_text(self, file_bytes: bytes, mime_type: str | None = None) -> OCRResult:
        if not file_bytes:
            raise ValueError("OCR_INPUT_EMPTY: File bytes are empty")

        mime = (mime_type or "").lower()
        is_pdf = mime == "application/pdf" or file_bytes.startswith(b"%PDF-")
        is_image = mime.startswith("image/") or any(
            file_bytes.startswith(sig)
            for sig in [b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*"]
        )

        if is_pdf:
            return await self._process_pdf(file_bytes)
        elif is_image:
            return await self._process_image(file_bytes)
        else:
            try:
                decoded = file_bytes.decode("utf-8")
                return OCRResult(
                    text=decoded,
                    confidence=None,
                    page_count=1,
                    engine="local_text",
                    pages=[{"page_number": 1, "text": decoded, "confidence": None}],
                )
            except Exception as exc:
                try:
                    return await self._process_image(file_bytes)
                except Exception:
                    raise ValueError(f"OCR_UNSUPPORTED_FORMAT: Unable to process file: {exc}") from exc

    async def _process_image(self, image_bytes: bytes) -> OCRResult:
        def _run_tesseract():
            if image_bytes.startswith(b"\xff\xd8\xff"):
                suffix = ".jpg"
            elif image_bytes.startswith(b"GIF8"):
                suffix = ".gif"
            elif image_bytes.startswith(b"BM"):
                suffix = ".bmp"
            elif image_bytes.startswith((b"II*\x00", b"MM\x00*")):
                suffix = ".tif"
            else:
                suffix = ".png"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name

            try:
                text, confidence = self._tesseract_image_data(tmp_path)
                return OCRResult(
                    text=text,
                    confidence=confidence,
                    page_count=1,
                    engine="tesseract_local",
                    pages=[{"page_number": 1, "text": text, "confidence": confidence}],
                )
            except FileNotFoundError as err:
                logger.error("Tesseract OCR executable is not installed or is missing from PATH")
                raise RuntimeError(
                    "TESSERACT_NOT_INSTALLED: install Tesseract OCR and make sure tesseract.exe is on the backend PATH, then restart the backend"
                ) from err
            except Exception as err:
                logger.error("Tesseract image processing failed error_type=%s", type(err).__name__)
                raise RuntimeError("OCR_IMAGE_PROCESSING_FAILED: image OCR failed") from err
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        return await asyncio.to_thread(_run_tesseract)

    async def _process_pdf(self, pdf_bytes: bytes) -> OCRResult:
        def _run_pdftoppm_and_tesseract():
            with tempfile.TemporaryDirectory() as tmp_dir:
                pdf_path = os.path.join(tmp_dir, "input.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)

                out_prefix = os.path.join(tmp_dir, "page")
                cmd_pdf = ["pdftoppm", "-png", "-r", "150", pdf_path, out_prefix]
                try:
                    subprocess.run(cmd_pdf, capture_output=True, check=True)
                except Exception as err:
                    logger.warning("pdftoppm conversion failed error_type=%s; retrying with direct tesseract", type(err).__name__)

                page_files = sorted(Path(tmp_dir).glob("page-*.png"))
                if not page_files:
                    try:
                        import pymupdf

                        page_data = []
                        with pymupdf.open(pdf_path) as pdf:
                            for page_number, page in enumerate(pdf, start=1):
                                image_path = os.path.join(tmp_dir, f"rendered-{page_number}.png")
                                page.get_pixmap(dpi=150).save(image_path)
                                text, confidence = self._tesseract_image_data(image_path)
                                page_data.append({
                                    "page_number": page_number,
                                    "text": text,
                                    "confidence": confidence,
                                })
                        text = "\n\n".join(page["text"] for page in page_data if page["text"].strip()).strip()
                        measured_pages = [page["confidence"] for page in page_data if page["confidence"] is not None]
                        return OCRResult(
                            text=text,
                            confidence=(sum(measured_pages) / len(measured_pages)) if measured_pages else None,
                            page_count=len(page_data),
                            engine="pymupdf_tesseract",
                            pages=page_data,
                        )
                    except Exception as err:
                        raise RuntimeError("OCR_PDF_PROCESSING_FAILED: PDF OCR failed") from err

                page_data = []
                for page_number, p_file in enumerate(page_files, start=1):
                    text, confidence = self._tesseract_image_data(str(p_file))
                    page_data.append({"page_number": page_number, "text": text, "confidence": confidence})

                combined_text = "\n\n".join(p["text"] for p in page_data if p["text"].strip()).strip()
                measured_pages = [p["confidence"] for p in page_data if p["confidence"] is not None]
                return OCRResult(
                    text=combined_text,
                    confidence=(sum(measured_pages) / len(measured_pages)) if measured_pages else None,
                    page_count=len(page_files),
                    engine="pdftoppm_tesseract",
                    pages=page_data,
                )

        return await asyncio.to_thread(_run_pdftoppm_and_tesseract)

    @staticmethod
    def _tesseract_image_data(image_path: str) -> tuple[str, float | None]:
        import pytesseract
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = _tesseract_executable()
        with Image.open(image_path) as image:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        words = []
        confidences = []
        for word, raw_confidence in zip(data.get("text", []), data.get("conf", [])):
            if not word or not word.strip():
                continue
            words.append(word)
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                continue
            if confidence != -1:
                confidences.append(confidence)
        text = " ".join(words).strip()
        average = (sum(confidences) / len(confidences) / 100.0) if confidences else None
        return text, average
