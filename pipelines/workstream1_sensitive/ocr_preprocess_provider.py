"""PreprocessOcrProvider — deskew/denoise/binarise (and rasterise PDFs) before OCR.

Recovers text from degraded scans that the raw image / image-only-PDF path returns empty
for. Sits behind the `OCRProvider` port: it rasterises a PDF to page images, preprocesses
each image, then OCRs it via the docling convert backend. The docling `ConvertClient` is
injectable so unit tests run with no container; the image libs are lazy (inside
`ocr_preprocess`). Only copies of the item bytes are handled; nothing is logged/persisted.
"""

from __future__ import annotations

from libs.schemas import ExceptionCode, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract_docling import (
    ConvertClient,
    HttpConvertClient,
    build_convert_payload,
)
from pipelines.workstream1_sensitive.ocr_preprocess import preprocess_image, rasterize_pdf


class PreprocessOcrProvider:
    def __init__(
        self,
        base_url: str,
        *,
        dpi: int = 300,
        deskew: bool = True,
        denoise: bool = True,
        binarize: bool = True,
        contrast: bool = True,
        sharpen: bool = True,
        sauvola_window: int = 25,
        client: ConvertClient | None = None,
    ) -> None:
        self._client = client if client is not None else HttpConvertClient(base_url)
        self._dpi = dpi
        self._deskew = deskew
        self._denoise = denoise
        self._binarize = binarize
        self._contrast = contrast
        self._sharpen = sharpen
        self._sauvola_window = sauvola_window

    @staticmethod
    def _is_pdf(entry: ManifestEntry, data: bytes) -> bool:
        return entry.content_type == "application/pdf" or data[:5] == b"%PDF-"

    def _ocr_png(self, entry: ManifestEntry, index: int, png: bytes) -> str:
        # docling detects format by filename → present the preprocessed page as a .png.
        page = entry.model_copy(update={"path": f"{entry.source_id}-p{index}.png"})
        try:
            response = self._client.convert(build_convert_payload(page, png))
        except PipelineItemError:
            raise
        except Exception as exc:  # transport/parse failure → typed, fail loud
            raise PipelineItemError(
                ExceptionCode.OCR_FAILURE, f"ocr service failed for {entry.source_id}"
            ) from exc
        document = response.get("document") or {}
        return str(document.get("text_content") or "").strip()

    def recognise(self, entry: ManifestEntry, data: bytes) -> str:
        try:
            pages = rasterize_pdf(data, self._dpi) if self._is_pdf(entry, data) else [data]
        except Exception as exc:  # rasterisation failure → typed, fail loud
            raise PipelineItemError(
                ExceptionCode.OCR_FAILURE, f"rasterise failed for {entry.source_id}"
            ) from exc
        texts: list[str] = []
        for index, page in enumerate(pages):
            try:
                cleaned = preprocess_image(
                    page,
                    deskew=self._deskew,
                    denoise=self._denoise,
                    binarize=self._binarize,
                    contrast=self._contrast,
                    sharpen=self._sharpen,
                    sauvola_window=self._sauvola_window,
                )
            except Exception as exc:  # preprocessing failure → typed, fail loud
                raise PipelineItemError(
                    ExceptionCode.OCR_FAILURE, f"preprocess failed for {entry.source_id}"
                ) from exc
            texts.append(self._ocr_png(entry, index, cleaned))
        text = "\n".join(part for part in texts if part).strip()
        if not text:
            raise PipelineItemError(
                ExceptionCode.OCR_FAILURE, f"no OCR text for {entry.source_id}"
            )
        return text
