"""Stage 1 — Ingest.

Verifies each item is authorised by the frozen manifest, reads it read-only, checks
its content hash, and confirms the content type is supported. Raises a typed
`PipelineItemError` otherwise (Contracts 1 and 4).
"""

from __future__ import annotations

from libs.hashing import sha256_hex
from libs.schemas import ExceptionCode, ManifestEntry
from libs.source.base import SourceReader
from pipelines.workstream1_sensitive.errors import PipelineItemError

SUPPORTED_TEXT_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/pdf",
        # Office Open XML (handled by the native engine; decode engine → OCR gate).
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)
OCR_TYPES = frozenset({"image/png", "image/jpeg", "image/tiff"})


def ingest(reader: SourceReader, entry: ManifestEntry) -> bytes:
    """Return the verified raw bytes for an authorised item."""
    if entry.content_type not in SUPPORTED_TEXT_TYPES | OCR_TYPES:
        raise PipelineItemError(
            ExceptionCode.UNSUPPORTED_TYPE,
            f"unsupported content_type for {entry.source_id}",
        )
    try:
        data = reader.open_item(entry.source_id)
    except KeyError as exc:
        raise PipelineItemError(
            ExceptionCode.NOT_IN_MANIFEST, str(exc)
        ) from exc
    except OSError as exc:
        raise PipelineItemError(
            ExceptionCode.UNREADABLE,
            f"could not read {entry.source_id}",
        ) from exc
    if sha256_hex(data) != entry.content_hash:
        raise PipelineItemError(
            ExceptionCode.HASH_MISMATCH,
            f"content hash mismatch for {entry.source_id}",
        )
    return data


def requires_ocr_type(entry: ManifestEntry) -> bool:
    """True when the content type is an image type handled by the OCR gate."""
    return entry.content_type in OCR_TYPES
