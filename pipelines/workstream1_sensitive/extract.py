"""Stage 2 — Extract: the `ExtractedText` contract, shared helpers, and the
`DecodeExtractor` (UTF-8 text-layer read).

`DecodeExtractor` is the skeleton default. Real engines — `NativeExtractor`
(in-venv) and the Docling/Tika HTTP adapters — implement the same `ExtractionEngine`
port. Extracted text is working data held in memory for this item only; it is never
logged or persisted (`.claude/rules/privacy-sensitive-data.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from libs.schemas import EvidenceLocation, ManifestEntry
from pipelines.workstream1_sensitive.ingest import requires_ocr_type


@dataclass
class ExtractedText:
    """In-memory extraction result. `text`/`spans` hold content — never persisted."""

    source_id: str
    text: str
    spans: list[tuple[EvidenceLocation, str]] = field(default_factory=list)
    has_text_layer: bool = False
    printable_ratio: float = 0.0
    image_coverage: float = 0.0
    coverage_complete: bool = False
    ocr_used: bool = False


def no_text_layer_result(source_id: str) -> ExtractedText:
    """Extraction result for an item with no usable text layer (→ OCR gate)."""
    return ExtractedText(
        source_id=source_id,
        text="",
        has_text_layer=False,
        printable_ratio=0.0,
        image_coverage=1.0,
        coverage_complete=False,
    )


def printable_ratio(text: str) -> float:
    """Fraction of characters that are printable (shared with the OCR gate)."""
    if not text:
        return 0.0
    printable = sum(1 for char in text if char.isprintable() or char in "\n\t ")
    return printable / len(text)


def line_spans(text: str) -> list[tuple[EvidenceLocation, str]]:
    spans: list[tuple[EvidenceLocation, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip("\n")
        if stripped:
            location = EvidenceLocation(
                char_start=offset, char_end=offset + len(stripped)
            )
            spans.append((location, stripped))
        offset += len(line)
    return spans


def text_result(
    source_id: str,
    text: str,
    spans: list[tuple[EvidenceLocation, str]],
    *,
    coverage_complete: bool,
    ocr_used: bool = False,
) -> ExtractedText:
    """Assemble an ExtractedText from recovered text + spans (shared by all engines)."""
    return ExtractedText(
        source_id=source_id,
        text=text,
        spans=spans,
        has_text_layer=bool(text.strip()),
        printable_ratio=printable_ratio(text),
        image_coverage=0.0,
        coverage_complete=coverage_complete,
        ocr_used=ocr_used,
    )


def decode_text(source_id: str, data: bytes) -> ExtractedText:
    """Build an ExtractedText by decoding bytes as UTF-8 (no layer → OCR gate)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return no_text_layer_result(source_id)
    return text_result(
        source_id, text, line_spans(text), coverage_complete=bool(text.strip())
    )


def resolve_location(
    match_start: int,
    match_end: int,
    spans: list[tuple[EvidenceLocation, str]],
    separator: str = "\n",
) -> EvidenceLocation:
    """Map a char offset in the flattened text to the owning span's location.

    Returns the span's structural anchor (page / sheet+cell) when it has one, else the
    precise char offsets. Falls back to char offsets when spans are absent.
    """
    cursor = 0
    for location, span_text in spans:
        span_end = cursor + len(span_text)
        if cursor <= match_start < span_end:
            if location.page is not None or location.sheet is not None:
                return location
            return EvidenceLocation(char_start=match_start, char_end=match_end)
        cursor = span_end + len(separator)
    return EvidenceLocation(char_start=match_start, char_end=match_end)


class DecodeExtractor:
    """Skeleton default: UTF-8 decode; image types defer to the OCR gate."""

    def extract(self, entry: ManifestEntry, data: bytes) -> ExtractedText:
        if requires_ocr_type(entry):
            return no_text_layer_result(entry.source_id)
        return decode_text(entry.source_id, data)
