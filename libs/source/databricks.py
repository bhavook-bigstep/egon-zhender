"""DatabricksSourceReader — read-only source over a Unity Catalog Volume.

Implements the `SourceReader` port: reads the frozen manifest (JSONL) and each document's
bytes from a UC volume via the Databricks SDK Files API. Read-only by construction — there
is no write/redact/merge path (Contract 1). Reading FROM the customer's Databricks is
in-boundary (not off-boundary egress). Logs reference source IDs + metadata only, never
document content (Contract 2).

The `files` client is injectable so unit tests run against a fake with no workspace; in
production it is `WorkspaceClient(profile=...).files`, lazily imported so `databricks-sdk`
is needed only for this backend.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from libs.schemas import ManifestEntry


@runtime_checkable
class FilesClient(Protocol):
    """The slice of `WorkspaceClient.files` this reader uses (download only)."""

    def download(self, file_path: str) -> Any:
        """Return a response whose `.contents` is a readable binary stream."""
        ...


class DatabricksSourceReader:
    """Read-only reader over a UC volume governed by a frozen manifest (JSONL)."""

    def __init__(
        self,
        root: str,
        manifest: str,
        profile: str | None = None,
        files: FilesClient | None = None,
    ) -> None:
        self._root = root.rstrip("/")  # e.g. /Volumes/workspace/prince_houston/ws1_golden
        self._manifest = manifest.lstrip("/")  # e.g. manifest.jsonl (relative to root)
        self._profile = profile
        self._files = files
        self._entries: dict[str, ManifestEntry] = {}
        self._loaded = False

    def _client(self) -> FilesClient:
        if self._files is None:
            from databricks.sdk import WorkspaceClient  # lazy: optional dependency

            self._files = WorkspaceClient(profile=self._profile).files
        return self._files

    def _download_bytes(self, path: str) -> bytes:
        response = self._client().download(path)
        data: bytes = response.contents.read()
        return data

    def _load(self) -> None:
        if self._loaded:
            return
        blob = self._download_bytes(f"{self._root}/{self._manifest}")
        for line in blob.decode("utf-8").splitlines():
            if line.strip():
                entry = ManifestEntry.model_validate_json(line)  # extra golden fields ignored
                self._entries[entry.source_id] = entry
        self._loaded = True

    def list_manifest(self) -> list[ManifestEntry]:
        self._load()
        return sorted(self._entries.values(), key=lambda entry: entry.source_id)

    def _entry(self, source_id: str) -> ManifestEntry:
        self._load()
        entry = self._entries.get(source_id)
        if entry is None:
            raise KeyError(f"source_id not in manifest: {source_id}")
        return entry

    def open_item(self, source_id: str) -> bytes:
        return self._download_bytes(f"{self._root}/{self._entry(source_id).path}")

    def open_stream(self, source_id: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        entry = self._entry(source_id)
        stream = self._client().download(f"{self._root}/{entry.path}").contents
        while chunk := stream.read(chunk_size):  # bounded chunks, never the whole file
            yield chunk
