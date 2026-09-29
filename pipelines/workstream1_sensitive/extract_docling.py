"""DoclingHttpExtractor — extraction via a docling-serve container.

POSTs the item bytes (base64) to `POST {base_url}/v1/convert/source` and reads
`document.text_content`. Docling handles born-digital PDF/DOCX/XLSX/HTML *and* scanned
pages (it OCRs internally), so this one engine covers the extract + OCR front door.
The HTTP client is injectable so unit tests run against a fake with no container.

The source bytes are a copy sent to a local service (Contract 1 unaffected); responses
are not logged verbatim (privacy rules).
"""

from __future__ import annotations

import base64
from typing import Any, Protocol, runtime_checkable

from libs.schemas import ExceptionCode, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract import (
    ExtractedText,
    line_spans,
    no_text_layer_result,
    text_result,
)


def build_convert_payload(entry: ManifestEntry, data: bytes) -> dict[str, Any]:
    """Docling /v1/convert/source request for one item (shared with the OCR provider)."""
    return {
        "sources": [
            {
                "kind": "file",
                "base64_string": base64.b64encode(data).decode("ascii"),
                "filename": entry.path,
            }
        ],
        "options": {"to_formats": ["text"]},
    }


@runtime_checkable
class ConvertClient(Protocol):
    def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a convert request to docling-serve and return the parsed JSON."""
        ...


class HttpConvertClient(ConvertClient):
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._url = base_url.rstrip("/") + "/v1/convert/source"
        self._timeout = timeout

    def convert(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx  # lazy

        response = httpx.post(self._url, json=payload, timeout=self._timeout)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


class DoclingHttpExtractor:
    def __init__(self, base_url: str, client: ConvertClient | None = None) -> None:
        self._client = client if client is not None else HttpConvertClient(base_url)

    def extract(self, entry: ManifestEntry, data: bytes) -> ExtractedText:
        try:
            response = self._client.convert(build_convert_payload(entry, data))
        except PipelineItemError:
            raise
        except Exception as exc:  # service/transport failure → typed, fail loud
            raise PipelineItemError(
                ExceptionCode.EXTRACTION_ERROR, f"docling convert failed for {entry.source_id}"
            ) from exc

        if response.get("status") == "failure":
            raise PipelineItemError(
                ExceptionCode.EXTRACTION_ERROR,
                f"docling reported failure for {entry.source_id}",
            )
        document = response.get("document") or {}
        text = (document.get("text_content") or document.get("md_content") or "").strip()
        if not text:
            return no_text_layer_result(entry.source_id)
        return text_result(
            entry.source_id,
            text,
            line_spans(text),
            coverage_complete=response.get("status") == "success",
        )
