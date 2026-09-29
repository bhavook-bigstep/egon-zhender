"""Factory selection + a run()-level test that exercises the native engine end-to-end."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
import yaml

from libs.schemas import OcrConfig, Ws1Config
from pipelines.workstream1_sensitive.ocr_gate import StubOCRProvider
from pipelines.workstream1_sensitive.ocr_http import HttpOcrProvider
from pipelines.workstream1_sensitive.runner import build_ocr, run


def _cfg(ocr: OcrConfig) -> Ws1Config:
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    model = Ws1Config(**base)
    return model.model_copy(update={"ocr": ocr})


def test_build_ocr_stub() -> None:
    assert isinstance(build_ocr(_cfg(OcrConfig(provider="stub"))), StubOCRProvider)


def test_build_ocr_docling_requires_url() -> None:
    with pytest.raises(ValueError):
        build_ocr(_cfg(OcrConfig(provider="docling")))


def test_build_ocr_docling_with_url() -> None:
    ocr = build_ocr(_cfg(OcrConfig(provider="docling", url="http://localhost:5001")))
    assert isinstance(ocr, HttpOcrProvider)


def test_build_ocr_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        build_ocr(_cfg(OcrConfig(provider="nope")))


def test_run_native_engine_end_to_end(tmp_path: Path) -> None:
    from docx import Document

    document = Document()
    document.add_paragraph("Client account reference ACCT-123456 confirmed.")
    buffer = io.BytesIO()
    document.save(buffer)
    data = buffer.getvalue()

    sample_dir = tmp_path / "sample"
    sample_dir.mkdir()
    (sample_dir / "note.docx").write_bytes(data)
    docx_mime = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    manifest = [
        {
            "source_id": "docx_1",
            "content_type": docx_mime,
            "content_hash": hashlib.sha256(data).hexdigest(),
            "path": "note.docx",
        }
    ]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["extract"]["engine"] = "native"
    base["source"]["root"] = str(sample_dir)
    base["source"]["manifest"] = str(tmp_path / "manifest.json")
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")

    result = run(cfg_path)
    assert result.reconcile.reconciled
    summary = result.summaries[0]
    assert summary.flag_status.value == "flagged"
    assert "financial" in summary.sensitivity_categories
