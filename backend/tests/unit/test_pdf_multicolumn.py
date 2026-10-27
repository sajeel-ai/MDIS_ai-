"""Unit tests for PDF multi-column reading order (Item 5).

Creates synthetic two-column PDFs with pymupdf and verifies the left-column
text appears before right-column text in the extracted output.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_two_column_pdf() -> bytes:
    """Return the bytes of a minimal two-column PDF created with pymupdf.

    Left column: "LEFT_COL_TEXT" inserted near x=50
    Right column: "RIGHT_COL_TEXT" inserted near x=350
    Both blocks are on the same vertical band so natural left-to-right reading
    would correctly place left before right.
    """
    import pymupdf  # type: ignore

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)  # A4

    # Insert left-column text block (multiple lines to ensure >= 20 chars)
    left_text = "LEFT_COL_TEXT alpha bravo charlie delta echo foxtrot"
    right_text = "RIGHT_COL_TEXT golf hotel india juliet kilo lima mike"

    # left column: x=50, y=100
    page.insert_text((50, 100), left_text, fontsize=12)
    # right column: x=350, y=100 (same vertical position)
    page.insert_text((350, 100), right_text, fontsize=12)

    pdf_bytes = doc.write()
    doc.close()
    return pdf_bytes


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMultiColumnSorting:
    def test_sort_blocks_multicolumn_basic(self):
        """_sort_blocks_multicolumn puts left-column blocks before right-column ones."""
        from app.providers.ocr.local import _sort_blocks_multicolumn

        page_width = 595.0
        # Simulate blocks: (x0, y0, x1, y1, "text", block_no, block_type)
        left_block = (50, 100, 200, 120, "Left column text here.", 0, 0)
        right_block = (350, 100, 500, 120, "Right column text here.", 1, 0)

        # Pass them in reverse order to ensure sorting fixes it
        blocks = [right_block, left_block]
        sorted_blks = _sort_blocks_multicolumn(blocks, page_width)

        assert len(sorted_blks) == 2
        assert sorted_blks[0][0] < sorted_blks[1][0]  # left x before right x

    def test_sort_blocks_filters_non_text(self):
        """Non-text blocks (type != 0) are excluded."""
        from app.providers.ocr.local import _sort_blocks_multicolumn

        page_width = 595.0
        text_block = (50, 100, 200, 120, "Text block", 0, 0)
        image_block = (350, 100, 500, 300, None, 1, 1)  # type 1 = image

        sorted_blks = _sort_blocks_multicolumn([text_block, image_block], page_width)
        assert len(sorted_blks) == 1
        assert sorted_blks[0][6] == 0  # type 0 = text

    def test_sort_blocks_same_column_sorted_by_y(self):
        """Within the same column, blocks are sorted top-to-bottom (by y)."""
        from app.providers.ocr.local import _sort_blocks_multicolumn

        page_width = 595.0
        top_left = (50, 80, 200, 100, "Top of left column", 0, 0)
        bottom_left = (50, 200, 200, 220, "Bottom of left column", 1, 0)

        sorted_blks = _sort_blocks_multicolumn([bottom_left, top_left], page_width)
        assert sorted_blks[0][1] < sorted_blks[1][1]  # smaller y first

    def test_two_column_pdf_left_before_right(self):
        """End-to-end: left column text appears before right column in extracted output."""
        import pymupdf  # type: ignore
        from app.providers.ocr.local import _sort_blocks_multicolumn

        pdf_bytes = _build_two_column_pdf()
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
            page = pdf[0]
            blocks = page.get_text("blocks")
            sorted_blks = _sort_blocks_multicolumn(blocks, page.rect.width)
            text = "\n".join(b[4].rstrip("\n") for b in sorted_blks).strip()

        left_pos = text.find("LEFT_COL_TEXT")
        right_pos = text.find("RIGHT_COL_TEXT")

        assert left_pos != -1, "LEFT_COL_TEXT not found in output"
        assert right_pos != -1, "RIGHT_COL_TEXT not found in output"
        assert left_pos < right_pos, (
            f"LEFT_COL_TEXT (pos {left_pos}) should appear before RIGHT_COL_TEXT (pos {right_pos})."
            f"\nFull output:\n{text}"
        )

    def test_empty_blocks_returns_empty(self):
        """Empty block list returns empty list."""
        from app.providers.ocr.local import _sort_blocks_multicolumn

        result = _sort_blocks_multicolumn([], 595.0)
        assert result == []

    def test_col_boundary_at_45_percent(self):
        """Boundary is 45% of page width; block at exactly boundary goes to right column."""
        from app.providers.ocr.local import _sort_blocks_multicolumn

        page_width = 200.0
        boundary = page_width * 0.45  # = 90.0
        # Block starting at x=90 → right column (not strictly less than 90)
        block_at_boundary = (90, 50, 150, 70, "Boundary text", 0, 0)
        block_left = (10, 50, 80, 70, "Left text", 1, 0)

        sorted_blks = _sort_blocks_multicolumn([block_at_boundary, block_left], page_width)
        # block_left is col 0, block_at_boundary is col 1
        assert sorted_blks[0][0] == 10   # left text first
        assert sorted_blks[1][0] == 90   # boundary text second

