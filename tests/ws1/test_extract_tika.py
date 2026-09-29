"""TikaHttpExtractor (fake Tika client — no container needed)."""

from __future__ import annotations

import pytest

from libs.schemas import ExceptionCode, ExtractConfig, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract_engine import build_extraction_engine
from pipelines.workstream1_sensitive.extract_tika import TikaHttpExtractor

ENTRY = ManifestEntry(
    source_id="x", content_type="application/msword", content_hash="h", path="legacy.doc"
)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_data: bytes | None = None

    def extract_text(self, data: bytes) -> str:
        self.last_data = data
        return self._text


def test_extracts_text() -> None:
    client = _FakeClient("Legacy doc with ACCT-123456 inside")
    extractor = TikaHttpExtractor("http://tika", client=client)
    result = extractor.extract(ENTRY, b"\xd0\xcf raw ole bytes")
    assert result.has_text_layer
    assert "ACCT-123456" in result.text
    assert client.last_data == b"\xd0\xcf raw ole bytes"


def test_empty_text_defers_to_ocr_gate() -> None:
    extractor = TikaHttpExtractor("http://tika", client=_FakeClient("   "))
    assert not extractor.extract(ENTRY, b"bytes").has_text_layer


def test_transport_error_becomes_typed_exception() -> None:
    class _Boom:
        def extract_text(self, data: bytes) -> str:
            raise ConnectionError("tika down")

    extractor = TikaHttpExtractor("http://tika", client=_Boom())
    with pytest.raises(PipelineItemError) as exc:
        extractor.extract(ENTRY, b"bytes")
    assert exc.value.code is ExceptionCode.EXTRACTION_ERROR


def test_factory_requires_url() -> None:
    with pytest.raises(ValueError):
        build_extraction_engine(ExtractConfig(engine="tika"))


def test_factory_builds_tika_with_url() -> None:
    engine = build_extraction_engine(ExtractConfig(engine="tika", tika_url="http://tika"))
    assert isinstance(engine, TikaHttpExtractor)
