"""Local OCR Provider using Tesseract 5 and pdftoppm for PDFs and Images."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.providers.ocr.base import BaseOCRProvider, OCRResult

logger = logging.getLogger(__name__)


def map_bbox_to_original(bbox, *, source_size, deskewed_size, processed_size, angle_degrees):
    """Map an axis-aligned final OCR box to the original image pixel space."""
    import math

    scale_x = deskewed_size[0] / processed_size[0]
    scale_y = deskewed_size[1] / processed_size[1]
    theta = math.radians(angle_degrees)
    cos_a, sin_a = math.cos(theta), math.sin(theta)
    source_cx, source_cy = source_size[0] / 2, source_size[1] / 2
    rotated_cx, rotated_cy = deskewed_size[0] / 2, deskewed_size[1] / 2
    left, top, right, bottom = bbox
    corners = []
    for px, py in ((left, top), (right, top), (left, bottom), (right, bottom)):
        rx, ry = px * scale_x - rotated_cx, py * scale_y - rotated_cy
        corners.append((cos_a * rx - sin_a * ry + source_cx, sin_a * rx + cos_a * ry + source_cy))
    return [
        max(0.0, min(point[0] for point in corners)),
        max(0.0, min(point[1] for point in corners)),
        min(float(source_size[0]), max(point[0] for point in corners)),
        min(float(source_size[1]), max(point[1] for point in corners)),
    ]


def _sort_blocks_multicolumn(blocks, page_width: float):
    """Sort text blocks by column (left/right) then top-to-bottom.

    Args:
        blocks: List of block tuples from ``page.get_text("blocks")``.
        page_width: Width of the PDF page in points.

    Returns:
        Sorted list of text blocks (type 0 only).
    """
    text_blocks = [b for b in blocks if b[6] == 0]  # type 0 = text
    col_boundary = page_width * 0.45  # blocks starting left of this are column 0
    return sorted(text_blocks, key=lambda b: (0 if b[0] < col_boundary else 1, b[1]))


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
                text, confidence, word_boxes = self._tesseract_image_data(tmp_path)
                return OCRResult(
                    text=text,
                    confidence=confidence,
                    page_count=1,
                    engine="tesseract_local",
                    pages=[{"page_number": 1, "text": text, "confidence": confidence, "word_boxes": word_boxes}],
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
        digital_result = self._extract_embedded_pdf_text(pdf_bytes)
        if digital_result is not None:
            return digital_result

        def _run_pdftoppm_and_tesseract():
            with tempfile.TemporaryDirectory() as tmp_dir:
                pdf_path = os.path.join(tmp_dir, "input.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)

                # Digital PDFs should retain their embedded Unicode text and
                # layout. OCR is only used for pages whose text layer is empty
                # or too small to be useful.
                try:
                    import pymupdf

                    with pymupdf.open(pdf_path) as pdf:
                        if pdf.page_count == 0:
                            raise RuntimeError("OCR_EMPTY_RESULT: PDF has no pages")
                        page_data = []
                        ocr_pages = []
                        for page_number, page in enumerate(pdf, start=1):
                            blocks = page.get_text("blocks")
                            sorted_blks = _sort_blocks_multicolumn(blocks, page.rect.width)
                            text = "\n".join(b[4].rstrip("\n") for b in sorted_blks).strip()
                            if not text:
                                text = (page.get_text("text", sort=True) or "").strip()
                            # A page with only a handful of non-whitespace
                            # characters is usually a scanned/image page.
                            useful = len("".join(text.split())) >= 20 and any(ch.isalnum() for ch in text)
                            if useful:
                                page_data.append({
                                    "page_number": page_number,
                                    "text": text.rstrip("\n"),
                                    "confidence": None,
                                    "method": "text_layer",
                                })
                            else:
                                ocr_pages.append((page_number, page.get_pixmap(dpi=150)))

                        for page_number, pixmap in ocr_pages:
                            image_path = os.path.join(tmp_dir, f"ocr-{page_number}.png")
                            pixmap.save(image_path)
                            text, confidence, word_boxes = self._tesseract_image_data(image_path)
                            page_data.append({
                                "page_number": page_number,
                                "text": text,
                                "confidence": confidence,
                                "word_boxes": word_boxes,
                                "method": "ocr",
                            })
                        page_data.sort(key=lambda page: page["page_number"])
                        combined_text = "\n\n".join(page["text"] for page in page_data if page["text"].strip()).strip()
                        if not combined_text:
                            raise RuntimeError("OCR_EMPTY_RESULT: PDF produced no usable text")
                        measured_pages = [page["confidence"] for page in page_data if page["confidence"] is not None]
                        methods = {page["method"] for page in page_data}
                        return OCRResult(
                            text=combined_text,
                            confidence=(sum(measured_pages) / len(measured_pages)) if measured_pages else None,
                            page_count=len(page_data),
                            engine="pymupdf_text_layer" if methods == {"text_layer"} else "pymupdf_text_layer_ocr",
                            pages=page_data,
                        )
                except RuntimeError:
                    raise
                except Exception as err:
                    logger.warning("PDF text-layer extraction failed error_type=%s; trying OCR fallback", type(err).__name__)

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
                                text, confidence, word_boxes = self._tesseract_image_data(image_path)
                                page_data.append({
                                    "page_number": page_number,
                                    "text": text,
                                    "confidence": confidence,
                                    "word_boxes": word_boxes,
                                    "method": "ocr",
                                })
                        text = "\n\n".join(page["text"] for page in page_data if page["text"].strip()).strip()
                        if not text:
                            raise RuntimeError("OCR_EMPTY_RESULT: PDF produced no usable text")
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
                    text, confidence, word_boxes = self._tesseract_image_data(str(p_file))
                    page_data.append({"page_number": page_number, "text": text, "confidence": confidence, "word_boxes": word_boxes, "method": "ocr"})

                combined_text = "\n\n".join(p["text"] for p in page_data if p["text"].strip()).strip()
                if not combined_text:
                    raise RuntimeError("OCR_EMPTY_RESULT: PDF produced no usable text")
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
    def _extract_embedded_pdf_text(pdf_bytes: bytes) -> OCRResult | None:
        """Read a complete embedded text layer without a lossy OCR round-trip."""
        try:
            import pymupdf

            with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
                if pdf.page_count == 0:
                    raise ValueError("OCR_EMPTY_RESULT: PDF has no pages")
                pages = []
                for page_number, page in enumerate(pdf, start=1):
                    blocks = page.get_text("blocks")
                    sorted_blks = _sort_blocks_multicolumn(blocks, page.rect.width)
                    text = "\n".join(b[4].rstrip("\n") for b in sorted_blks).strip()
                    if not text:
                        text = (page.get_text("text", sort=True) or "").strip()
                    useful = len("".join(text.split())) >= 20 and any(ch.isalnum() for ch in text)
                    if not useful:
                        return None
                    pages.append({"page_number": page_number, "text": text, "confidence": None, "method": "text_layer"})
                combined = "\n\n".join(page["text"] for page in pages).strip()
                if not combined:
                    raise ValueError("OCR_EMPTY_RESULT: PDF produced no usable text")
                return OCRResult(text=combined, confidence=None, page_count=len(pages), engine="pymupdf_text_layer", pages=pages)
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("PDF embedded text read failed error_type=%s", type(exc).__name__)
            return None

    @staticmethod
    def _tesseract_image_data(image_path: str) -> tuple[str, float | None, list[dict[str, object]]]:
        import math

        import numpy as np
        import pytesseract
        from PIL import Image

        from app.config import settings as _settings
        from app.providers.ocr.preprocessing import preprocess_image_with_transform

        pytesseract.pytesseract.tesseract_cmd = _tesseract_executable()
        with Image.open(image_path) as _raw_image:
            original_size = _raw_image.size
            # Item 3: normalise non-standard TIFF modes before any other step
            image = _raw_image
            if image.mode in ("I;16", "I;16B", "I", "F"):
                arr = np.array(image, dtype=np.float32)
                arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-9) * 255
                image = Image.fromarray(arr.astype(np.uint8), mode="L")
            elif image.mode == "CMYK":
                image = image.convert("RGB")
            elif image.mode == "P":
                image = image.convert("RGBA").convert("RGB")

            # Item 1: preprocessing pipeline (deskew / denoise / contrast / binarize)
            image, deskew_angle = preprocess_image_with_transform(image, _settings)

            # Item 2: memory cap — downscale oversized images
            w, h = image.size
            pre_resize_size = (w, h)
            pixels = w * h
            if pixels > _settings.ocr_max_image_pixels:
                scale = math.sqrt(_settings.ocr_max_image_pixels / pixels)
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                image = image.resize((new_w, new_h), Image.LANCZOS)

            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        words = []
        confidences = []
        word_boxes = []
        word_confidences = []
        text_cursor = 0
        final_w, final_h = image.size
        for index, (word, raw_confidence) in enumerate(zip(data.get("text", []), data.get("conf", []))):
            if not word or not word.strip():
                continue
            words.append(word)
            if text_cursor:
                text_cursor += 1
            left, top = float(data["left"][index]), float(data["top"][index])
            right, bottom = left + float(data["width"][index]), top + float(data["height"][index])
            box = map_bbox_to_original(
                (left, top, right, bottom),
                source_size=original_size,
                deskewed_size=pre_resize_size,
                processed_size=(final_w, final_h),
                angle_degrees=deskew_angle,
            )
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                confidence = None
            if confidence is not None and confidence != -1:
                confidences.append(confidence)
                word_confidences.append(confidence / 100.0)
            else:
                word_confidences.append(None)
            original_w, original_h = original_size
            word_boxes.append({
                "text": word,
                "bounding_box": [round(v, 2) for v in box],
                "bbox": [round(box[0] / original_w, 6), round(box[1] / original_h, 6), round(box[2] / original_w, 6), round(box[3] / original_h, 6)],
                "start_offset": text_cursor,
                "end_offset": text_cursor + len(word),
                "confidence": confidence / 100.0 if confidence is not None and confidence >= 0 else None,
            })
            text_cursor += len(word)
        text = " ".join(words).strip()
        average = (sum(confidences) / len(confidences) / 100.0) if confidences else None
        return text, average, word_boxes

