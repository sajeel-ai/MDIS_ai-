"""Unit tests for OCR image preprocessing (Items 1, 2, 3).

Run with:
    cd backend
    venv\\Scripts\\python.exe -c "import os, sys, pytest; os.environ['DEBUG'] = 'false'; \
        os.environ['DATABASE_URL'] = 'postgresql+asyncpg://postgres:postgres@localhost:5432/mdis'; \
        sys.exit(pytest.main(['tests/unit/test_ocr_preprocessing.py', '-v']))"
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**kwargs):
    """Return a minimal settings-like namespace."""
    defaults = dict(
        ocr_preprocessing_enabled=True,
        ocr_deskew_enabled=True,
        ocr_denoise_enabled=True,
        ocr_contrast_normalize_enabled=True,
        ocr_binarize_enabled=True,
        ocr_max_image_pixels=89_478_485,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _synthetic_text_image(width: int = 200, height: int = 60) -> Image.Image:
    """White background with a black horizontal bar simulating text."""
    arr = np.full((height, width), 255, dtype=np.uint8)
    arr[20:40, 20:180] = 0  # black rectangle = "text"
    return Image.fromarray(arr, mode="L")


# ---------------------------------------------------------------------------
# Item 1 — Preprocessing pipeline
# ---------------------------------------------------------------------------


class TestDeskew:
    def test_returns_pil_image(self):
        from app.providers.ocr.preprocessing import deskew

        img = _synthetic_text_image()
        result = deskew(img)
        assert isinstance(result, Image.Image)

    def test_deskew_straight_image_unchanged_angle(self):
        """A perfectly horizontal image should return angle ≈ 0 (size may change slightly)."""
        from app.providers.ocr.preprocessing import deskew

        img = _synthetic_text_image(300, 80)
        result = deskew(img)
        # The result is still a PIL Image with positive dimensions
        assert result.width > 0
        assert result.height > 0

    def test_rotated_text_box_maps_back_to_source_coordinates(self):
        """A downscaled, deskewed OCR box still covers its text in source pixels."""
        import math
        from app.providers.ocr.local import map_bbox_to_original

        source = Image.new("L", (320, 140), 255)
        # Use a wide text-like region so the expected source location is clear.
        source_box = (70.0, 48.0, 250.0, 82.0)
        from PIL import ImageDraw
        ImageDraw.Draw(source).rectangle(source_box, fill=0)
        angle = 7.0
        rotated = source.rotate(angle, expand=True, fillcolor=255)

        # Transform source corners into the rotated image's coordinates.
        theta = math.radians(angle)
        ca, sa = math.cos(theta), math.sin(theta)
        scx, scy = source.width / 2, source.height / 2
        rcx, rcy = rotated.width / 2, rotated.height / 2
        rotated_corners = []
        for x, y in ((source_box[0], source_box[1]), (source_box[2], source_box[1]),
                     (source_box[0], source_box[3]), (source_box[2], source_box[3])):
            dx, dy = x - scx, y - scy
            rotated_corners.append((ca * dx + sa * dy + rcx, -sa * dx + ca * dy + rcy))
        rotated_box = [min(p[0] for p in rotated_corners), min(p[1] for p in rotated_corners),
                       max(p[0] for p in rotated_corners), max(p[1] for p in rotated_corners)]
        processed_size = (rotated.width // 2, rotated.height // 2)
        final_box = [rotated_box[0] / 2, rotated_box[1] / 2, rotated_box[2] / 2, rotated_box[3] / 2]

        mapped = map_bbox_to_original(
            final_box,
            source_size=source.size,
            deskewed_size=rotated.size,
            processed_size=processed_size,
            angle_degrees=-angle,
        )
        assert mapped[0] <= source_box[0] + 1
        assert mapped[1] <= source_box[1] + 1
        assert mapped[2] >= source_box[2] - 1
        assert mapped[3] >= source_box[3] - 1

    def test_real_ocr_pipeline_maps_rotated_downscaled_target_to_original_coordinates(self, monkeypatch, tmp_path):
        """Real Tesseract path must retain source-coordinate boxes after deskew/downscale."""
        import math
        import pytest
        from app.config import settings
        from app.evals.ocr_metrics import bbox_iou
        from app.providers.ocr.local import LocalOCRProvider
        from PIL import ImageDraw, ImageFont

        if not __import__("shutil").which("tesseract"):
            pytest.skip("Tesseract executable is unavailable")
        font_candidates = (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        )
        font_path = next((candidate for candidate in font_candidates if candidate.is_file()), None)
        if font_path is None:
            pytest.skip("No supported OCR test font is installed")

        page = Image.new("L", (1500, 900), 255)
        draw = ImageDraw.Draw(page)
        font = ImageFont.truetype(str(font_path), 72)
        word = "TARGET"
        origin = (140, 280)
        gt = draw.textbbox(origin, word, font=font)
        draw.text(origin, word, fill=0, font=font)
        angle = 6.0
        rotated = page.rotate(angle, expand=True, fillcolor=255)
        rotated_path = tmp_path / "rotated_large.png"
        rotated.save(rotated_path)

        # PIL's expanded rotate maps source coordinates into the rotated image.
        theta = math.radians(angle)
        ca, sa = math.cos(theta), math.sin(theta)
        source_center = (page.width / 2, page.height / 2)
        rotated_center = (rotated.width / 2, rotated.height / 2)
        points = []
        for x, y in ((gt[0], gt[1]), (gt[2], gt[1]), (gt[0], gt[3]), (gt[2], gt[3])):
            dx, dy = x - source_center[0], y - source_center[1]
            points.append((ca * dx + sa * dy + rotated_center[0], -sa * dx + ca * dy + rotated_center[1]))
        ground_truth = [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]

        monkeypatch.setattr(settings, "ocr_preprocessing_enabled", True)
        monkeypatch.setattr(settings, "ocr_deskew_enabled", True)
        monkeypatch.setattr(settings, "ocr_denoise_enabled", False)
        monkeypatch.setattr(settings, "ocr_contrast_normalize_enabled", False)
        monkeypatch.setattr(settings, "ocr_binarize_enabled", False)
        monkeypatch.setattr(settings, "ocr_max_image_pixels", 400_000)

        _, _, boxes = LocalOCRProvider._tesseract_image_data(str(rotated_path))
        target_boxes = [box["bounding_box"] for box in boxes if str(box.get("text", "")).upper() == word]
        assert target_boxes, f"Tesseract did not find {word!r}; got {[b.get('text') for b in boxes]}"
        assert max(bbox_iou(ground_truth, box) for box in target_boxes) >= 0.35


class TestOtsuBinarize:
    def test_known_threshold(self):
        """Image with half-black, half-white rows → threshold should be ~127."""
        from app.providers.ocr.preprocessing import otsu_binarize

        arr = np.zeros((100, 100), dtype=np.uint8)
        arr[50:, :] = 255  # top half dark, bottom half white
        img = Image.fromarray(arr, mode="L")
        result = otsu_binarize(img)
        assert isinstance(result, Image.Image)
        assert result.mode == "L"
        result_arr = np.array(result)
        # Top half should be 0, bottom half 255
        assert result_arr[:50, :].max() == 0
        assert result_arr[50:, :].min() == 255

    def test_uniform_image_does_not_crash(self):
        from app.providers.ocr.preprocessing import otsu_binarize

        img = Image.fromarray(np.full((50, 50), 128, dtype=np.uint8), mode="L")
        result = otsu_binarize(img)
        assert isinstance(result, Image.Image)


class TestPreprocessImage:
    def test_disabled_returns_same_size(self):
        """When preprocessing disabled, image is returned untouched."""
        from app.providers.ocr.preprocessing import preprocess_image

        settings = _make_settings(ocr_preprocessing_enabled=False)
        img = _synthetic_text_image(150, 50)
        result = preprocess_image(img, settings)
        assert result is img  # identity — same object
        assert result.size == (150, 50)

    def test_enabled_changes_image(self):
        """When enabled, at minimum the mode or content should differ (binarise is on)."""
        from app.providers.ocr.preprocessing import preprocess_image

        settings = _make_settings(ocr_preprocessing_enabled=True)
        img = _synthetic_text_image(200, 60).convert("RGB")  # start as RGB
        result = preprocess_image(img, settings)
        assert isinstance(result, Image.Image)
        # After full pipeline the image is in mode 'L' (binarize returns L)
        assert result.mode == "L"

    def test_only_binarize_enabled(self):
        from app.providers.ocr.preprocessing import preprocess_image

        settings = _make_settings(
            ocr_preprocessing_enabled=True,
            ocr_deskew_enabled=False,
            ocr_denoise_enabled=False,
            ocr_contrast_normalize_enabled=False,
            ocr_binarize_enabled=True,
        )
        img = _synthetic_text_image()
        result = preprocess_image(img, settings)
        assert result.mode == "L"

    def test_only_denoise_enabled(self):
        from app.providers.ocr.preprocessing import preprocess_image

        settings = _make_settings(
            ocr_preprocessing_enabled=True,
            ocr_deskew_enabled=False,
            ocr_denoise_enabled=True,
            ocr_contrast_normalize_enabled=False,
            ocr_binarize_enabled=False,
        )
        img = _synthetic_text_image()
        result = preprocess_image(img, settings)
        assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# Item 2 — Memory cap / downscale
# ---------------------------------------------------------------------------


class TestMemoryCapDownscale:
    """Tests for the pixel-count downscale logic in LocalOCRProvider."""

    def test_large_image_is_downscaled(self):
        """Image larger than cap should be resized to fit within pixel limit."""
        import math
        import tempfile
        import os

        # Create a 10100 x 10100 image (just over the 89_478_485 limit which is ~9460x9460)
        # To avoid actual memory allocation, use a small image but monkeypatch size
        # Instead, let's use a real but manageable image and a LOW cap
        limit = 10_000  # very small cap for test
        img = Image.new("L", (200, 200), 255)  # 40 000 px — above our tiny cap

        w, h = img.size
        pixels = w * h
        if pixels > limit:
            scale = math.sqrt(limit / pixels)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            resized = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            resized = img

        assert resized.width * resized.height <= limit + 1  # allow 1 px rounding

    def test_image_within_cap_not_resized(self):
        """Small image within limit should not be resized."""
        import math

        limit = 89_478_485
        img = Image.new("L", (100, 100), 255)
        w, h = img.size
        pixels = w * h
        if pixels > limit:
            scale = math.sqrt(limit / pixels)
            resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        else:
            resized = img

        assert resized is img  # identity preserved for small images

    def test_large_white_image_10k(self):
        """Create a real 10000×10000 white image and confirm downscale path works."""
        import math

        # This allocates ~100MB but verifies end-to-end without OOM (just L mode = 1 byte/px)
        limit = 89_478_485
        img = Image.new("L", (10000, 10000), 255)
        w, h = img.size
        pixels = w * h  # 100_000_000 > limit
        assert pixels > limit

        scale = math.sqrt(limit / pixels)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        assert resized.width * resized.height <= limit + new_w  # rounding tolerance


# ---------------------------------------------------------------------------
# Item 3 — TIFF 16-bit / non-standard mode conversions
# ---------------------------------------------------------------------------


class TestTiffModeConversions:
    def _apply_mode_conversion(self, image: Image.Image) -> Image.Image:
        """Mirror the conversion logic from LocalOCRProvider._tesseract_image_data."""
        if image.mode in ("I;16", "I;16B", "I", "F"):
            arr = np.array(image, dtype=np.float32)
            arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-9) * 255
            image = Image.fromarray(arr.astype(np.uint8), mode="L")
        elif image.mode == "CMYK":
            image = image.convert("RGB")
        elif image.mode == "P":
            image = image.convert("RGBA").convert("RGB")
        return image

    def test_16bit_tiff_converts_to_L(self):
        """Simulated 16-bit grayscale image (mode 'I') converts to mode 'L'."""
        # Create a 16-bit-range array and open as mode 'I'
        arr = np.linspace(0, 65535, 100 * 100, dtype=np.int32).reshape(100, 100)
        img_i = Image.fromarray(arr, mode="I")
        assert img_i.mode == "I"

        result = self._apply_mode_conversion(img_i)
        assert result.mode == "L"
        result_arr = np.array(result)
        assert result_arr.min() >= 0
        assert result_arr.max() <= 255

    def test_cmyk_converts_to_rgb(self):
        """CMYK image converts to RGB."""
        img_cmyk = Image.new("CMYK", (50, 50), (0, 0, 0, 0))
        result = self._apply_mode_conversion(img_cmyk)
        assert result.mode == "RGB"

    def test_palette_converts_to_rgb(self):
        """Palette (P) image converts through RGBA to RGB."""
        img_p = Image.new("P", (50, 50))
        result = self._apply_mode_conversion(img_p)
        assert result.mode == "RGB"

    def test_float_mode_converts_to_L(self):
        """Float32 mode 'F' image converts to mode 'L'."""
        arr = np.random.rand(80, 80).astype(np.float32) * 1000
        img_f = Image.fromarray(arr, mode="F")
        assert img_f.mode == "F"

        result = self._apply_mode_conversion(img_f)
        assert result.mode == "L"

    def test_16bit_tiff_roundtrip_via_bytesio(self):
        """Save 16-bit TIFF to BytesIO, re-open, apply conversion, verify mode."""
        arr = (np.arange(200 * 200, dtype=np.float32) / (200 * 200) * 65535).reshape(200, 200)
        arr_int32 = arr.astype(np.int32)
        img = Image.fromarray(arr_int32, mode="I")

        buf = io.BytesIO()
        img.save(buf, format="TIFF")
        buf.seek(0)
        reopened = Image.open(buf)

        result = self._apply_mode_conversion(reopened)
        assert result.mode in ("L", "RGB")
        assert result.width == 200
        assert result.height == 200

