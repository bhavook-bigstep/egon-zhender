"""Tests for ocr_preprocess — image cleanup and PDF rasterisation.

Heavy deps (PIL, numpy, skimage, pypdfium2, reportlab) may not be installed; each test
importorskips them at the top so the suite skips cleanly when a dep is absent. Fixtures
are synthetic and built in-memory (no PII, no files on disk).
"""

from __future__ import annotations

import pytest

from pipelines.workstream1_sensitive.ocr_preprocess import (
    preprocess_image,
    rasterize_pdf,
)


def _synthetic_png_bytes() -> bytes:
    """Build a small synthetic grayscale image with black rectangles as PNG bytes."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.new("L", (120, 60), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 12, 100, 20), fill=0)
    draw.rectangle((10, 30, 80, 38), fill=0)
    draw.rectangle((10, 46, 60, 52), fill=0)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_preprocess_image_returns_reopenable_png_and_is_deterministic() -> None:
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    pytest.importorskip("skimage")

    from io import BytesIO

    source = _synthetic_png_bytes()

    result = preprocess_image(source)
    assert isinstance(result, bytes)
    assert len(result) > 0

    with Image.open(BytesIO(result)) as reopened:
        reopened.load()
        assert reopened.size[0] > 0 and reopened.size[1] > 0

    # Determinism: same input -> identical bytes.
    again = preprocess_image(source)
    assert result == again


def test_preprocess_image_honours_disabled_stages() -> None:
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    pytest.importorskip("skimage")

    from io import BytesIO

    source = _synthetic_png_bytes()
    result = preprocess_image(source, deskew=False, denoise=False, binarize=False)
    assert isinstance(result, bytes)
    assert len(result) > 0
    with Image.open(BytesIO(result)) as reopened:
        reopened.load()
        assert reopened.mode == "L"


def test_blur_recovery_sharpens_edges() -> None:
    """The contrast+sharpen path restores edge contrast a Gaussian blur smears, so blurred
    text is recoverable where the un-sharpened path leaves it mushy. Deterministic."""
    pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    pytest.importorskip("skimage")

    from io import BytesIO

    import numpy as np
    from PIL import Image, ImageFilter

    # Build a heavily-blurred version of the synthetic page.
    with Image.open(BytesIO(_synthetic_png_bytes())) as base:
        blurred = base.convert("L").filter(ImageFilter.GaussianBlur(radius=3))
    blurred_buf = BytesIO()
    blurred.save(blurred_buf, format="PNG")
    blurred_png = blurred_buf.getvalue()

    def edge_energy(png: bytes) -> float:
        with Image.open(BytesIO(png)) as img:
            arr = np.asarray(img.convert("L"), dtype=np.float64)
        return float(np.var(np.diff(arr, axis=1)))  # horizontal gradient variance

    recovered = preprocess_image(blurred_png, deskew=False, contrast=True, sharpen=True)
    mushy = preprocess_image(
        blurred_png, deskew=False, contrast=False, sharpen=False, binarize=False
    )
    # Sharpen+contrast+binarise yields crisper edges than leaving the blur untouched.
    assert edge_energy(recovered) > edge_energy(mushy)
    # Deterministic.
    assert preprocess_image(blurred_png, deskew=False) == preprocess_image(
        blurred_png, deskew=False
    )


def test_rasterize_pdf_returns_one_png_per_page() -> None:
    pytest.importorskip("pypdfium2")
    pytest.importorskip("PIL.Image")
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")

    from io import BytesIO

    buffer = BytesIO()
    pdf_canvas = reportlab_canvas.Canvas(buffer)
    pdf_canvas.drawString(72, 720, "Synthetic page for rasterisation test")
    pdf_canvas.showPage()
    pdf_canvas.save()
    pdf_bytes = buffer.getvalue()

    pages = rasterize_pdf(pdf_bytes, dpi=100)
    assert isinstance(pages, list)
    assert len(pages) == 1
    assert isinstance(pages[0], bytes)
    assert len(pages[0]) > 0
