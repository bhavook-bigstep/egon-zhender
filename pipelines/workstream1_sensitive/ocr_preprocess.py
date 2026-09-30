"""Image preprocessing and PDF rasterisation to improve OCR on degraded scans.

Two deterministic helpers used ahead of the OCR stage:

- ``preprocess_image`` cleans a single raster image (grayscale, deskew, denoise,
  adaptive binarise) so a downstream OCR engine sees a sharper, level, high-contrast
  page.
- ``rasterize_pdf`` renders each PDF page to a PNG so scanned PDFs (no text layer) can
  be preprocessed and OCR'd page by page.

All heavy libraries (PIL, numpy, skimage, pypdfium2) are lazy-imported *inside* the
functions, so importing this module carries no ML dependency. No image content is
logged; both functions are deterministic (no randomness).
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # typing only; the runtime import is lazy inside each function
    from PIL import Image as PILImage

# Candidate skew angles (degrees) scanned during deskew; fixed for determinism.
_SKEW_ANGLE_RANGE_DEG: float = 5.0
_SKEW_ANGLE_STEP_DEG: float = 0.5


def preprocess_image(
    data: bytes, *, deskew: bool = True, denoise: bool = True, binarize: bool = True
) -> bytes:
    """Grayscale -> (deskew) -> (median denoise) -> (Sauvola adaptive binarise) -> PNG bytes.

    Deterministic. Lazy-imports PIL, numpy, skimage.
    """
    from PIL import Image, ImageFilter  # lazy: optional ML dep

    with Image.open(BytesIO(data)) as opened:
        image = opened.convert("L")

        if deskew:
            angle = _estimate_skew_angle(image)
            if angle != 0.0:
                image = image.rotate(angle, expand=True, fillcolor=255)

        if denoise:
            image = image.filter(ImageFilter.MedianFilter(size=3))

        if binarize:
            image = _sauvola_binarize(image)

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def rasterize_pdf(data: bytes, dpi: int = 200) -> list[bytes]:
    """Render each PDF page to PNG bytes via pypdfium2 (lazy import). Deterministic."""
    import pypdfium2 as pdfium  # lazy: optional ML dep

    scale = dpi / 72.0
    pages_png: list[bytes] = []
    pdf = pdfium.PdfDocument(data)
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                bitmap = page.render(scale=scale)
                try:
                    pil_image = bitmap.to_pil()
                    buffer = BytesIO()
                    pil_image.save(buffer, format="PNG")
                    pages_png.append(buffer.getvalue())
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        pdf.close()
    return pages_png


def _estimate_skew_angle(image: PILImage.Image) -> float:
    """Estimate skew via row-sum projection variance over fixed candidate angles.

    Text lines maximise the variance of the horizontal projection (row sums) when the
    page is level, so the angle giving the highest variance is the skew to correct.
    Deterministic: fixed candidate grid, no randomness. Lazy-imports numpy.
    """
    import numpy as np  # lazy: optional ML dep
    from PIL import Image  # lazy: optional ML dep

    # Coarse binarisation (ink = dark) so projection reflects text rows, not shading.
    array = np.asarray(image, dtype=np.float64)
    ink = (array < 128.0).astype(np.float64)

    best_angle = 0.0
    best_variance = -1.0
    steps = int(round(_SKEW_ANGLE_RANGE_DEG / _SKEW_ANGLE_STEP_DEG))
    for step in range(-steps, steps + 1):
        angle = step * _SKEW_ANGLE_STEP_DEG
        rotated = Image.fromarray((ink * 255.0).astype(np.uint8)).rotate(
            angle, expand=False, fillcolor=0
        )
        projection = np.asarray(rotated, dtype=np.float64).sum(axis=1)
        variance = float(np.var(projection))
        if variance > best_variance:
            best_variance = variance
            best_angle = angle
    return best_angle


def _sauvola_binarize(image: PILImage.Image) -> PILImage.Image:
    """Apply Sauvola adaptive thresholding, returning a black/white ('L') image.

    Lazy-imports numpy and skimage.
    """
    import numpy as np  # lazy: optional ML dep
    from PIL import Image  # lazy: optional ML dep
    from skimage.filters import threshold_sauvola  # lazy: optional ML dep

    array = np.asarray(image, dtype=np.float64)
    threshold = threshold_sauvola(array)
    binary = array > threshold
    return Image.fromarray((binary * 255).astype(np.uint8), mode="L")
