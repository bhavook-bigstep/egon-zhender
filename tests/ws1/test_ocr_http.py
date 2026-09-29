"""HttpOcrProvider (fake docling convert client — no container needed)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.schemas import ExceptionCode, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.ocr_http import HttpOcrProvider

ENTRY = ManifestEntry(
    source_id="x", content_type="image/png", content_hash="h", path="scan.png"
)


class _FakeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.last_payload: dict[str, Any] | None = None

    def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_payload = payload
        return self._response


def test_recognises_text() -> None:
    client = _FakeClient(
        {"status": "success", "document": {"text_content": "GOVID-AB123456 scanned"}}
    )
    provider = HttpOcrProvider("http://docling", client=client)
    text = provider.recognise(ENTRY, b"\x89PNG image bytes")
    assert "GOVID-AB123456" in text
    assert client.last_payload["sources"][0]["kind"] == "file"


def test_empty_text_raises_ocr_failure() -> None:
    client = _FakeClient({"status": "success", "document": {"text_content": ""}})
    provider = HttpOcrProvider("http://docling", client=client)
    with pytest.raises(PipelineItemError) as exc:
        provider.recognise(ENTRY, b"bytes")
    assert exc.value.code is ExceptionCode.OCR_FAILURE


def test_transport_error_raises_ocr_failure() -> None:
    class _Boom:
        def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise ConnectionError("down")

    provider = HttpOcrProvider("http://docling", client=_Boom())
    with pytest.raises(PipelineItemError) as exc:
        provider.recognise(ENTRY, b"bytes")
    assert exc.value.code is ExceptionCode.OCR_FAILURE
