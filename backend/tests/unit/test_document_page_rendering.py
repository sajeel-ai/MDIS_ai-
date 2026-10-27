from io import BytesIO

import pytest
import pymupdf
from PIL import Image

from app.routers.documents import render_page_png


def test_page_image_rendering_is_bounded_and_does_not_need_plaintext_temp_files():
    original = Image.new("RGB", (3200, 1600), "white")
    source = BytesIO()
    original.save(source, format="PNG")
    rendered = Image.open(BytesIO(render_page_png(source.getvalue(), "image/png", 1)))
    assert rendered.size == (2048, 1024)


def test_pdf_page_renders_in_memory_and_rejects_missing_page():
    document = pymupdf.open()
    document.new_page(width=612, height=792)
    data = document.tobytes()
    document.close()
    rendered = Image.open(BytesIO(render_page_png(data, "application/pdf", 1)))
    assert rendered.size[0] <= 2048 and rendered.size[1] <= 2048
    with pytest.raises(ValueError, match="Document page not found"):
        render_page_png(data, "application/pdf", 2)
