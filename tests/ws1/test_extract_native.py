"""NativeExtractor: real DOCX/XLSX (built in-test) and PDF (reportlab if present)."""

from __future__ import annotations

import io

import pytest

from libs.schemas import ExceptionCode, ExtractConfig, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract_engine import build_extraction_engine
from pipelines.workstream1_sensitive.extract_native import DOCX, PDF, XLSX, NativeExtractor

EXTRACTOR = NativeExtractor()
TOKEN = "ACCT-123456"


def _entry(content_type: str) -> ManifestEntry:
    return ManifestEntry(
        source_id="x", content_type=content_type, content_hash="h", path="p"
    )


def test_native_docx_extracts_real_text() -> None:
    from docx import Document

    document = Document()
    document.add_paragraph(f"Client reference {TOKEN} confirmed.")
    buffer = io.BytesIO()
    document.save(buffer)

    result = EXTRACTOR.extract(_entry(DOCX), buffer.getvalue())
    assert result.has_text_layer
    assert TOKEN in result.text
    assert result.spans


def test_native_xlsx_extracts_cell_with_location() -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active["B2"] = f"account {TOKEN}"
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = EXTRACTOR.extract(_entry(XLSX), buffer.getvalue())
    assert TOKEN in result.text
    assert any(loc.cell == "B2" for loc, _ in result.spans)


def test_native_pdf_extracts_text_if_reportlab_present() -> None:
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, f"Statement reference {TOKEN}")
    pdf.showPage()
    pdf.save()

    result = EXTRACTOR.extract(_entry(PDF), buffer.getvalue())
    assert result.has_text_layer
    assert TOKEN in result.text
    assert any(loc.page == 1 for loc, _ in result.spans)


def test_native_scanned_pdf_no_text_layer_defers_to_ocr() -> None:
    # Bytes that are not a parseable PDF text layer → no_text_layer (OCR gate handles).
    result = EXTRACTOR.extract(_entry("image/png"), b"\x89PNG\x00binary")
    assert not result.has_text_layer


def test_native_text_plain_uses_decode_path() -> None:
    result = EXTRACTOR.extract(_entry("text/plain"), b"note with ACCT-123456 inside")
    assert result.has_text_layer
    assert TOKEN in result.text


def test_native_corrupt_pdf_raises_extraction_error() -> None:
    with pytest.raises(PipelineItemError) as exc:
        EXTRACTOR.extract(_entry(PDF), b"this is not a pdf")
    assert exc.value.code is ExceptionCode.EXTRACTION_ERROR


def test_native_corrupt_docx_raises_extraction_error() -> None:
    with pytest.raises(PipelineItemError) as exc:
        EXTRACTOR.extract(_entry(DOCX), b"this is not a docx zip")
    assert exc.value.code is ExceptionCode.EXTRACTION_ERROR


def test_native_corrupt_xlsx_raises_extraction_error() -> None:
    with pytest.raises(PipelineItemError) as exc:
        EXTRACTOR.extract(_entry(XLSX), b"this is not an xlsx zip")
    assert exc.value.code is ExceptionCode.EXTRACTION_ERROR


def test_factory_selects_native_and_decode() -> None:
    from pipelines.workstream1_sensitive.extract import DecodeExtractor

    assert isinstance(build_extraction_engine(ExtractConfig(engine="native")), NativeExtractor)
    assert isinstance(build_extraction_engine(ExtractConfig(engine="decode")), DecodeExtractor)


def test_factory_rejects_unwired_and_unknown_engines() -> None:
    with pytest.raises(ValueError):
        build_extraction_engine(ExtractConfig(engine="docling"))
    with pytest.raises(ValueError):
        build_extraction_engine(ExtractConfig(engine="nope"))
