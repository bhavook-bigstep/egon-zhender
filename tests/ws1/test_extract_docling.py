"""DoclingHttpExtractor (fake convert client — no container needed)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.schemas import ExceptionCode, ExtractConfig, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract_docling import DoclingHttpExtractor
from pipelines.workstream1_sensitive.extract_engine import build_extraction_engine

ENTRY = ManifestEntry(
    source_id="x", content_type="application/pdf", content_hash="h", path="doc.pdf"
)


class _FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.last_payload: dict[str, Any] | None = None

    def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_payload = payload
        return self._response


def test_success_returns_text_and_sends_base64() -> None:
    client = _FakeClient(
        {"status": "success", "document": {"text_content": "Ref ACCT-123456 ok"}}
    )
    extractor = DoclingHttpExtractor("http://docling", client=client)
    result = extractor.extract(ENTRY, b"%PDF-1.4 real bytes")
    assert result.has_text_layer
    assert "ACCT-123456" in result.text
    assert result.coverage_complete
    assert client.last_payload is not None
    source = client.last_payload["sources"][0]
    assert source["kind"] == "file"
    assert source["filename"] == "doc.pdf"
    assert "base64_string" in source
    assert client.last_payload["options"]["to_formats"] == ["text"]


def test_empty_text_defers_to_ocr_gate() -> None:
    client = _FakeClient({"status": "success", "document": {"text_content": "   "}})
    extractor = DoclingHttpExtractor("http://docling", client=client)
    result = extractor.extract(ENTRY, b"bytes")
    assert not result.has_text_layer


def test_failure_status_raises_extraction_error() -> None:
    client = _FakeClient({"status": "failure", "document": {}})
    extractor = DoclingHttpExtractor("http://docling", client=client)
    with pytest.raises(PipelineItemError) as exc:
        extractor.extract(ENTRY, b"bytes")
    assert exc.value.code is ExceptionCode.EXTRACTION_ERROR


def test_transport_error_becomes_typed_exception() -> None:
    class _Boom:
        def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise ConnectionError("service down")

    extractor = DoclingHttpExtractor("http://docling", client=_Boom())
    with pytest.raises(PipelineItemError) as exc:
        extractor.extract(ENTRY, b"bytes")
    assert exc.value.code is ExceptionCode.EXTRACTION_ERROR


def test_factory_requires_url() -> None:
    with pytest.raises(ValueError):
        build_extraction_engine(ExtractConfig(engine="docling"))


def test_factory_builds_docling_with_url() -> None:
    engine = build_extraction_engine(
        ExtractConfig(engine="docling", docling_url="http://docling")
    )
    assert isinstance(engine, DoclingHttpExtractor)
