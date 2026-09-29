"""DecodeExtractor: text-layer detection and coverage (skeleton default)."""

from __future__ import annotations

from libs.schemas import ManifestEntry
from pipelines.workstream1_sensitive.extract import DecodeExtractor

EXTRACTOR = DecodeExtractor()


def _entry(content_type: str) -> ManifestEntry:
    return ManifestEntry(
        source_id="x", content_type=content_type, content_hash="h", path="p"
    )


def test_extract_text_layer() -> None:
    result = EXTRACTOR.extract(_entry("text/plain"), b"line one\nline two\n")
    assert result.has_text_layer
    assert result.printable_ratio > 0.9
    assert result.spans
    assert result.coverage_complete


def test_extract_image_has_no_text_layer() -> None:
    result = EXTRACTOR.extract(_entry("image/png"), b"\x89PNG\x00\x01")
    assert not result.has_text_layer
    assert result.image_coverage == 1.0


def test_extract_non_utf8_bytes_no_layer() -> None:
    result = EXTRACTOR.extract(_entry("application/pdf"), b"\xff\xfe\x00binary")
    assert not result.has_text_layer
    assert not result.coverage_complete
