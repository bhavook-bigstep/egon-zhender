"""Ingest stage: manifest gating, hash check, unsupported types."""

from __future__ import annotations

import pytest

from libs.hashing import sha256_hex
from libs.schemas import ExceptionCode, ManifestEntry
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.ingest import ingest
from tests.ws1.conftest import DictReader


def _entry(source_id: str, content_type: str, data: bytes) -> ManifestEntry:
    return ManifestEntry(
        source_id=source_id,
        content_type=content_type,
        content_hash=sha256_hex(data),
        path="p",
    )


def test_ingest_ok_returns_bytes() -> None:
    data = b"hello ACCT-123456"
    entry = _entry("a", "text/plain", data)
    reader = DictReader([entry], {"a": data})
    assert ingest(reader, entry) == data


def test_ingest_hash_mismatch() -> None:
    data = b"hello"
    entry = ManifestEntry(
        source_id="a", content_type="text/plain", content_hash="deadbeef", path="p"
    )
    reader = DictReader([entry], {"a": data})
    with pytest.raises(PipelineItemError) as exc:
        ingest(reader, entry)
    assert exc.value.code is ExceptionCode.HASH_MISMATCH


def test_ingest_unsupported_type() -> None:
    data = b"\x00\x01"
    entry = _entry("a", "application/octet-stream", data)
    reader = DictReader([entry], {"a": data})
    with pytest.raises(PipelineItemError) as exc:
        ingest(reader, entry)
    assert exc.value.code is ExceptionCode.UNSUPPORTED_TYPE


def test_ingest_not_in_manifest() -> None:
    data = b"hi"
    entry = _entry("a", "text/plain", data)
    reader = DictReader([entry], {})  # blob missing → open_item raises KeyError
    with pytest.raises(PipelineItemError) as exc:
        ingest(reader, entry)
    assert exc.value.code is ExceptionCode.NOT_IN_MANIFEST


class _RaisingReader:
    """A reader whose open_item raises OSError (unreadable item)."""

    def list_manifest(self) -> list[ManifestEntry]:
        return []

    def open_item(self, source_id: str) -> bytes:
        raise OSError("permission denied")


def test_ingest_unreadable_oserror() -> None:
    entry = _entry("a", "text/plain", b"x")
    with pytest.raises(PipelineItemError) as exc:
        ingest(_RaisingReader(), entry)
    assert exc.value.code is ExceptionCode.UNREADABLE
