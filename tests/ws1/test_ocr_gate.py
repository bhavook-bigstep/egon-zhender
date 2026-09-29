"""OCR gate: decision branches and the stub OCR provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from libs.schemas import ExceptionCode, ManifestEntry, OcrGateConfig
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract import ExtractedText
from pipelines.workstream1_sensitive.ocr_gate import (
    StubOCRProvider,
    apply_ocr_gate,
    needs_ocr,
)

CFG = OcrGateConfig()


def _extracted(
    text: str = "hello world of text",
    has_text_layer: bool = True,
    printable_ratio: float = 1.0,
    image_coverage: float = 0.0,
) -> ExtractedText:
    return ExtractedText(
        source_id="x",
        text=text,
        has_text_layer=has_text_layer,
        printable_ratio=printable_ratio,
        image_coverage=image_coverage,
        coverage_complete=has_text_layer,
    )


def test_needs_ocr_false_for_good_text() -> None:
    assert needs_ocr(_extracted(), CFG) is False


def test_needs_ocr_true_when_no_layer() -> None:
    assert (
        needs_ocr(
            _extracted(text="", has_text_layer=False, printable_ratio=0.0, image_coverage=1.0),
            CFG,
        )
        is True
    )


def test_needs_ocr_true_low_printable_ratio() -> None:
    assert needs_ocr(_extracted(printable_ratio=0.5), CFG) is True


def test_needs_ocr_true_high_image_coverage() -> None:
    assert needs_ocr(_extracted(image_coverage=0.9), CFG) is True


def test_needs_ocr_true_low_density() -> None:
    assert needs_ocr(_extracted(text="a" + " " * 100), CFG) is True


def test_apply_ocr_gate_reads_sidecar(tmp_path: Path) -> None:
    (tmp_path / "img.png.ocr.txt").write_text(
        "recognised GOVID-AB123456 text", encoding="utf-8"
    )
    entry = ManifestEntry(
        source_id="x", content_type="image/png", content_hash="h", path="img.png"
    )
    extracted = _extracted(text="", has_text_layer=False, printable_ratio=0.0, image_coverage=1.0)
    out = apply_ocr_gate(entry, extracted, CFG, StubOCRProvider(tmp_path), b"")
    assert out.ocr_used
    assert out.has_text_layer


def test_apply_ocr_gate_missing_sidecar_raises(tmp_path: Path) -> None:
    entry = ManifestEntry(
        source_id="x", content_type="image/png", content_hash="h", path="none.png"
    )
    extracted = _extracted(text="", has_text_layer=False, printable_ratio=0.0, image_coverage=1.0)
    with pytest.raises(PipelineItemError) as exc:
        apply_ocr_gate(entry, extracted, CFG, StubOCRProvider(tmp_path), b"")
    assert exc.value.code is ExceptionCode.OCR_FAILURE


def test_apply_ocr_gate_skips_when_text_ok(tmp_path: Path) -> None:
    entry = ManifestEntry(
        source_id="x", content_type="text/plain", content_hash="h", path="p"
    )
    extracted = _extracted()
    out = apply_ocr_gate(entry, extracted, CFG, StubOCRProvider(tmp_path), b"")
    assert out.ocr_used is False
    assert out is extracted
