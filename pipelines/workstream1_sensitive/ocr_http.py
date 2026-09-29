"""HttpOcrProvider — OCR via the docling-serve container (reused as OCR backend).

Posts the image bytes to docling's convert endpoint and returns the recognised text,
behind the existing `OCRProvider` port. Reuses the docling `ConvertClient`, so no extra
service is needed for OCR. The image bytes are a copy sent to a local service.
"""

from __future__ import annotations

from libs.schemas import ExceptionCode, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract_docling import (
    ConvertClient,
    HttpConvertClient,
    build_convert_payload,
)


class HttpOcrProvider:
    def __init__(self, base_url: str, client: ConvertClient | None = None) -> None:
        self._client = client if client is not None else HttpConvertClient(base_url)

    def recognise(self, entry: ManifestEntry, data: bytes) -> str:
        try:
            response = self._client.convert(build_convert_payload(entry, data))
        except PipelineItemError:
            raise
        except Exception as exc:
            raise PipelineItemError(
                ExceptionCode.OCR_FAILURE, f"ocr service failed for {entry.source_id}"
            ) from exc
        document = response.get("document") or {}
        text = (document.get("text_content") or "").strip()
        if response.get("status") == "failure" or not text:
            raise PipelineItemError(
                ExceptionCode.OCR_FAILURE, f"no OCR text for {entry.source_id}"
            )
        return text
