"""TikaHttpExtractor — extraction via an Apache Tika container.

PUTs the item bytes to `{base_url}/tika` (Accept: text/plain) and returns the extracted
text. Tika handles legacy/binary office formats (.doc/.xls) and many others, removing the
host Java requirement. The HTTP client is injectable so unit tests run without a container.
The source bytes are a copy sent to a local service; responses are not logged verbatim.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from libs.schemas import ExceptionCode, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract import (
    ExtractedText,
    line_spans,
    no_text_layer_result,
    text_result,
)


@runtime_checkable
class TikaClient(Protocol):
    def extract_text(self, data: bytes) -> str:
        """PUT bytes to Tika and return the extracted plain text."""
        ...


class HttpTikaClient(TikaClient):
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._url = base_url.rstrip("/") + "/tika"
        self._timeout = timeout

    def extract_text(self, data: bytes) -> str:
        import httpx  # lazy

        response = httpx.put(
            self._url,
            content=data,
            headers={"Accept": "text/plain"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.text


class TikaHttpExtractor:
    def __init__(self, base_url: str, client: TikaClient | None = None) -> None:
        self._client = client if client is not None else HttpTikaClient(base_url)

    def extract(self, entry: ManifestEntry, data: bytes) -> ExtractedText:
        try:
            text = self._client.extract_text(data).strip()
        except PipelineItemError:
            raise
        except Exception as exc:  # service/transport failure → typed, fail loud
            raise PipelineItemError(
                ExceptionCode.EXTRACTION_ERROR, f"tika extract failed for {entry.source_id}"
            ) from exc
        if not text:
            return no_text_layer_result(entry.source_id)
        return text_result(entry.source_id, text, line_spans(text), coverage_complete=True)
