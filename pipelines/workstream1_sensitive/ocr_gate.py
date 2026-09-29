"""Stage 3 — OCR gate.

OCR is the expensive stage, so it runs only when the text layer is absent or fails
quality checks — text density, printable ratio, and image coverage (WS1 CLAUDE.md;
performance rules). The gate decision and quality measures are recorded by the runner.

Skeleton depth: the gate logic is real; the OCR engine is a stub (`StubOCRProvider`)
that reads a co-located `<path>.ocr.txt` fixture, simulating recognised text without a
real engine. PaddleOCR replaces it behind the `OCRProvider` port in a later plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from libs.schemas import ExceptionCode, ManifestEntry, OcrGateConfig
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract import (
    ExtractedText,
    line_spans,
    printable_ratio,
)


@runtime_checkable
class OCRProvider(Protocol):
    def recognise(self, entry: ManifestEntry, data: bytes) -> str:
        """Return recognised text for an image item, or raise on failure."""
        ...


class StubOCRProvider(OCRProvider):
    """Simulates OCR by reading a co-located `<path>.ocr.txt` sidecar, read-only."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def recognise(self, entry: ManifestEntry, data: bytes) -> str:
        sidecar = self._root / (entry.path + ".ocr.txt")
        if not sidecar.exists():
            raise PipelineItemError(
                ExceptionCode.OCR_FAILURE,
                f"no OCR result available for {entry.source_id}",
            )
        with sidecar.open("r", encoding="utf-8") as handle:  # read-only
            return handle.read()


def _text_density(text: str) -> float:
    if not text:
        return 0.0
    non_space = sum(1 for char in text if not char.isspace())
    return non_space / len(text)


def needs_ocr(extracted: ExtractedText, cfg: OcrGateConfig) -> bool:
    """Decide whether the OCR engine must run for this item."""
    if not extracted.has_text_layer:
        return True
    if extracted.printable_ratio < cfg.min_printable_ratio:
        return True
    if extracted.image_coverage > cfg.max_image_coverage:
        return True
    if _text_density(extracted.text) < cfg.min_text_density:
        return True
    return False


def apply_ocr_gate(
    entry: ManifestEntry,
    extracted: ExtractedText,
    cfg: OcrGateConfig,
    ocr: OCRProvider,
    data: bytes,
) -> ExtractedText:
    """Return the (possibly OCR-augmented) extraction after the gate decision."""
    if not needs_ocr(extracted, cfg):
        return extracted
    text = ocr.recognise(entry, data)  # may raise PipelineItemError(OCR_FAILURE)
    return ExtractedText(
        source_id=entry.source_id,
        text=text,
        spans=line_spans(text),
        has_text_layer=bool(text.strip()),
        printable_ratio=printable_ratio(text),
        image_coverage=0.0,
        coverage_complete=bool(text.strip()),
        ocr_used=True,
    )
