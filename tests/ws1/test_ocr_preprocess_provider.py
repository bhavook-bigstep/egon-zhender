"""PreprocessOcrProvider (fake docling client; image libs stubbed — no ML deps needed)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.schemas import ManifestEntry
from pipelines.workstream1_sensitive import ocr_preprocess_provider as opp
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.ocr_preprocess_provider import PreprocessOcrProvider


def _entry(path: str, content_type: str) -> ManifestEntry:
    return ManifestEntry(source_id="x", content_type=content_type, content_hash="h", path=path)


class _FakeClient:
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self.calls: list[dict[str, Any]] = []

    def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        index = len(self.calls)
        self.calls.append(payload)
        return {"status": "success", "document": {"text_content": self._texts[index]}}


def _no_raster(_data: bytes, _dpi: int) -> list[bytes]:
    raise AssertionError("rasterize_pdf must not run for an image")


def test_pdf_rasterized_preprocessed_and_ocred(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opp, "rasterize_pdf", lambda data, dpi: [b"p0", b"p1"])
    monkeypatch.setattr(opp, "preprocess_image", lambda data, **kw: b"clean-" + data)
    client = _FakeClient(["hello", "world"])
    provider = PreprocessOcrProvider("http://x", client=client)
    text = provider.recognise(_entry("doc.pdf", "application/pdf"), b"%PDF-1.4")
    assert text == "hello\nworld"
    assert len(client.calls) == 2  # one OCR call per rasterised page


def test_image_single_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opp, "rasterize_pdf", _no_raster)
    monkeypatch.setattr(opp, "preprocess_image", lambda data, **kw: data)
    client = _FakeClient(["text here"])
    provider = PreprocessOcrProvider("http://x", client=client)
    assert provider.recognise(_entry("img.png", "image/png"), b"\x89PNG") == "text here"


def test_empty_ocr_raises_ocr_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(opp, "rasterize_pdf", lambda data, dpi: [b"p0"])
    monkeypatch.setattr(opp, "preprocess_image", lambda data, **kw: data)
    provider = PreprocessOcrProvider("http://x", client=_FakeClient([""]))
    with pytest.raises(PipelineItemError):
        provider.recognise(_entry("doc.pdf", "application/pdf"), b"%PDF-")


def test_build_ocr_selects_preprocess() -> None:
    from libs.config import load_ws1_config
    from pipelines.workstream1_sensitive.runner import build_ocr

    cfg = load_ws1_config("config/ws1.databricks.yaml")
    assert isinstance(build_ocr(cfg), PreprocessOcrProvider)
