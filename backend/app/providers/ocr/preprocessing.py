"""OCR Image Preprocessing — PIL + numpy only (no opencv, no scipy).

Pipeline
--------
deskew -> denoise -> contrast_normalize -> otsu_binarize

All functions accept and return PIL Images.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageFilter, ImageOps

if TYPE_CHECKING:
    from app.config import Settings


# ---------------------------------------------------------------------------
# Individual preprocessing steps
# ---------------------------------------------------------------------------


def deskew_with_angle(img: Image.Image) -> tuple[Image.Image, float]:
    """Rotate image to the angle that maximises horizontal projection variance.

    Scans -10 .. +10 degrees in 0.5-degree steps and picks the angle whose
    horizontal projection profile has the highest variance (a strong indicator
    of aligned text rows).

    Args:
        img: Input PIL Image (any mode).

    Returns:
        Deskewed PIL Image (same mode as input, filled with white).
    """
    gray = img.convert("L")
    arr = np.array(gray, dtype=np.float32)

    best_angle = 0.0
    best_variance = -1.0

    angles = [a * 0.5 for a in range(-20, 21)]  # -10.0 to +10.0 inclusive
    for angle in angles:
        # Rotate a grayscale copy
        rotated = gray.rotate(angle, expand=True, fillcolor=255)
        r_arr = np.array(rotated, dtype=np.float32)
        # Horizontal projection profile: mean intensity per row
        row_sums = r_arr.mean(axis=1)
        variance = float(np.var(row_sums))
        if variance > best_variance:
            best_variance = variance
            best_angle = angle

    if best_angle == 0.0:
        return img, 0.0

    # Apply the best angle to the original (colour-safe)
    # Determine fill colour: white-ish for RGB/RGBA, 255 for L
    if img.mode in ("RGB", "RGBA"):
        fill = (255, 255, 255) if img.mode == "RGB" else (255, 255, 255, 255)
    else:
        fill = 255

    return img.rotate(best_angle, expand=True, fillcolor=fill), best_angle


def deskew(img: Image.Image) -> Image.Image:
    """Compatibility wrapper returning only the deskewed image."""
    return deskew_with_angle(img)[0]


def denoise(img: Image.Image) -> Image.Image:
    """Apply a 3×3 median filter to reduce salt-and-pepper noise.

    Works on grayscale; converts to L, filters, returns L image.

    Args:
        img: Input PIL Image.

    Returns:
        Denoised PIL Image in mode 'L'.
    """
    gray = img.convert("L")
    return gray.filter(ImageFilter.MedianFilter(size=3))


def contrast_normalize(img: Image.Image) -> Image.Image:
    """Auto-contrast stretch with 2 % cutoff to normalise exposure.

    Uses PIL ImageOps.autocontrast — clips the darkest and lightest 2 % of
    pixels and remaps the rest to [0, 255].

    Args:
        img: Input PIL Image (any mode).

    Returns:
        Contrast-normalised PIL Image (mode 'L').
    """
    gray = img.convert("L")
    return ImageOps.autocontrast(gray, cutoff=2)


def otsu_binarize(img: Image.Image) -> Image.Image:
    """Binarise a grayscale image using Otsu's global threshold.

    Computes the threshold via a numpy histogram and applies it to produce
    a binary (0/255) image in mode 'L'.

    Args:
        img: Input PIL Image (converted to 'L' internally).

    Returns:
        Binary PIL Image in mode 'L'.
    """
    gray = img.convert("L")
    arr = np.array(gray, dtype=np.uint8)

    # Build normalised histogram
    hist, _ = np.histogram(arr.flatten(), bins=256, range=(0, 256))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return gray

    prob = hist / total

    # Otsu's method: maximise inter-class variance
    best_threshold = 0
    best_variance = -1.0
    cumulative_weight = 0.0
    cumulative_mean = 0.0
    global_mean = float(np.dot(np.arange(256), prob))

    for t in range(256):
        cumulative_weight += prob[t]
        cumulative_mean += t * prob[t]

        if cumulative_weight == 0 or cumulative_weight == 1:
            continue

        w_bg = cumulative_weight
        w_fg = 1.0 - cumulative_weight
        mean_bg = cumulative_mean / w_bg
        mean_fg = (global_mean - cumulative_mean) / w_fg

        variance = w_bg * w_fg * (mean_bg - mean_fg) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = t

    binary = (arr > best_threshold).astype(np.uint8) * 255
    return Image.fromarray(binary, mode="L")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def preprocess_image(img: Image.Image, settings: "Settings") -> Image.Image:
    """Apply enabled preprocessing steps in order.

    Order: deskew → denoise → contrast_normalize → otsu_binarize.

    If ``settings.ocr_preprocessing_enabled`` is False the original image is
    returned unchanged.

    Args:
        img: Input PIL Image.
        settings: App settings object (pydantic-settings).

    Returns:
        Preprocessed PIL Image, or the original if preprocessing is disabled.
    """
    return preprocess_image_with_transform(img, settings)[0]


def preprocess_image_with_transform(img: Image.Image, settings: "Settings") -> tuple[Image.Image, float]:
    """Preprocess an image and return the applied PIL deskew angle in degrees."""
    if not settings.ocr_preprocessing_enabled:
        return img, 0.0

    result = img
    deskew_angle = 0.0

    if settings.ocr_deskew_enabled:
        result, deskew_angle = deskew_with_angle(result)

    if settings.ocr_denoise_enabled:
        result = denoise(result)

    if settings.ocr_contrast_normalize_enabled:
        result = contrast_normalize(result)

    if settings.ocr_binarize_enabled:
        result = otsu_binarize(result)

    return result, deskew_angle

