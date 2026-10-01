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

# The allow-list matches what the configured extraction engine can read. Plain text and
# markup are read directly (decode/native); the legacy binary office + email formats need a
# rich engine (Tika/Docling) — under the `decode` default they reach the OCR gate and, if
# unreadable there, become a TYPED unable_to_process (never a silent drop). The point is that
# these formats are no longer rejected at ingest before the engine that CAN read them sees them.
TEXT_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "text/rtf",
    }
)
DOCUMENT_TYPES = frozenset(
    {
        "application/pdf",
        # Office Open XML (native engine reads docx/xlsx; Docling reads pptx).
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
        # Legacy binary office + OpenDocument + email — Tika / Docling.
        "application/msword",  # .doc
        "application/vnd.ms-excel",  # .xls
        "application/vnd.ms-powerpoint",  # .ppt
        "application/rtf",  # .rtf (alt MIME)
        "application/vnd.oasis.opendocument.text",  # .odt
        "application/vnd.oasis.opendocument.spreadsheet",  # .ods
        "message/rfc822",  # email .eml
    }
)
SUPPORTED_TEXT_TYPES = TEXT_TYPES | DOCUMENT_TYPES
OCR_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/tiff", "image/bmp", "image/gif", "image/webp"}
)


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
