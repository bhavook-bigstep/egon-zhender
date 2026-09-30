"""DatabricksSourceReader: reads manifest + items from a UC volume (fake client)."""

from __future__ import annotations

import io

import pytest

from libs.source.databricks import DatabricksSourceReader

_ROOT = "/Volumes/c/s/v"
_MANIFEST = (
    '{"source_id":"a1","content_type":"text/plain","content_hash":"h1",'
    '"path":"documents/a1.txt","scanned":false,"expected_flag_status":"flagged"}\n'
    '{"source_id":"a2","content_type":"application/pdf","content_hash":"h2",'
    '"path":"documents/a2.pdf"}\n'
)


class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self.contents = io.BytesIO(data)


class _FakeFiles:
    """Stand-in for WorkspaceClient.files — download only (read-only)."""

    def __init__(self, blobs: dict[str, bytes]) -> None:
        self._blobs = blobs
        self.downloaded: list[str] = []

    def download(self, file_path: str) -> _FakeResp:
        self.downloaded.append(file_path)
        return _FakeResp(self._blobs[file_path])


def _reader(blobs: dict[str, bytes]) -> tuple[DatabricksSourceReader, _FakeFiles]:
    fake = _FakeFiles(blobs)
    return DatabricksSourceReader(_ROOT, "manifest.jsonl", files=fake), fake


def test_list_manifest_parses_jsonl_ignoring_extra_fields() -> None:
    reader, _ = _reader({f"{_ROOT}/manifest.jsonl": _MANIFEST.encode()})
    entries = reader.list_manifest()
    assert [e.source_id for e in entries] == ["a1", "a2"]  # sorted, extra fields ignored
    assert entries[0].path == "documents/a1.txt"


def test_open_item_and_stream_download_the_right_paths() -> None:
    reader, fake = _reader(
        {
            f"{_ROOT}/manifest.jsonl": _MANIFEST.encode(),
            f"{_ROOT}/documents/a1.txt": b"hello world bytes",
        }
    )
    assert reader.open_item("a1") == b"hello world bytes"
    assert b"".join(reader.open_stream("a1", chunk_size=4)) == b"hello world bytes"
    assert f"{_ROOT}/documents/a1.txt" in fake.downloaded


def test_unknown_source_id_raises() -> None:
    reader, _ = _reader({f"{_ROOT}/manifest.jsonl": _MANIFEST.encode()})
    with pytest.raises(KeyError):
        reader.open_item("does-not-exist")


def test_reader_exposes_no_write_path() -> None:
    reader, _ = _reader({f"{_ROOT}/manifest.jsonl": _MANIFEST.encode()})
    for method in ("write", "put", "upload", "delete", "overwrite", "save"):
        assert not hasattr(reader, method)  # read-only by construction (Contract 1)
