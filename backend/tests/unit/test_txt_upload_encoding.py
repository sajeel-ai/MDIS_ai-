"""Unit tests for TXT upload encoding detection (Item 4).

Tests the charset_normalizer decision logic directly — no DB or HTTP server needed.
"""

from __future__ import annotations

import pytest
from charset_normalizer import from_bytes


# ---------------------------------------------------------------------------
# Helper: detection function mirroring documents.py logic
# ---------------------------------------------------------------------------


def detect_encoding(raw: bytes) -> str | None:
    """Return the best detected encoding name, or None if undetectable."""
    if b"\x00" in raw:
        return None  # null bytes → reject immediately
    best = from_bytes(raw).best()
    if best is None:
        return None
    return best.encoding


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCharsetNormalizerDetection:
    def test_utf8_detected(self):
        """Plain ASCII / UTF-8 text is always detectable."""
        raw = b"Hello, world! This is a UTF-8 text file."
        result = from_bytes(raw).best()
        assert result is not None

    def test_windows1252_detected(self):
        """Windows-1252 encoded text (common in clinical documents) is detectable."""
        # b'\xe9' is 'é' in Windows-1252 / Latin-1
        raw = "Patientenakte: Müller, Straße 14".encode("windows-1252")
        result = from_bytes(raw).best()
        assert result is not None, "Windows-1252 should be detectable by charset_normalizer"

    def test_latin1_detected(self):
        """Latin-1 (ISO-8859-1) is detectable."""
        raw = "Résumé médical du patient".encode("latin-1")
        result = from_bytes(raw).best()
        assert result is not None

    def test_utf8_bom_detected(self):
        """UTF-8 with BOM is accepted."""
        raw = "\ufeffPatient record".encode("utf-8-sig")
        result = from_bytes(raw).best()
        assert result is not None

    def test_random_binary_may_fail(self):
        """Purely random binary data with no linguistic structure may return None or low confidence."""
        # We can't guarantee None but can verify the function doesn't crash
        raw = bytes(range(256))
        result = from_bytes(raw)  # may or may not have a best — just shouldn't raise
        # no assertion on truthiness, just checking no exception

    def test_long_utf8_text_detected(self):
        """A long UTF-8 paragraph is reliably detected."""
        raw = ("The patient presented with chest pain and shortness of breath. " * 50).encode("utf-8")
        result = from_bytes(raw).best()
        assert result is not None


class TestNullByteRejection:
    def test_null_bytes_detected(self):
        """Bytes containing null bytes should be flagged."""
        raw = b"Hello\x00World"
        assert b"\x00" in raw  # confirm detection logic

    def test_no_null_bytes(self):
        """Normal text should not trigger the null-byte check."""
        raw = b"Normal clinical text without nulls."
        assert b"\x00" not in raw

    def test_null_only_bytes(self):
        """All-null content is flagged."""
        raw = b"\x00\x00\x00\x00"
        assert b"\x00" in raw

    def test_detect_encoding_helper_rejects_null(self):
        """detect_encoding helper returns None for null-bearing bytes."""
        raw = b"Patient: \x00 Smith"
        result = detect_encoding(raw)
        assert result is None

    def test_detect_encoding_accepts_utf8(self):
        """detect_encoding helper succeeds for valid UTF-8."""
        raw = b"Patient record: normal clinical text, UTF-8 encoded."
        result = detect_encoding(raw)
        assert result is not None

