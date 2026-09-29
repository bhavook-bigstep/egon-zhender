"""SampleTestEnvReader — the PoC-now read-only source adapter.

Reads a frozen manifest and the synthetic sample files it authorises. Files are
opened in binary read mode only; there is no write path (Contract 1).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from libs.schemas import ManifestEntry


class SampleTestEnvReader:
    """Read-only reader over `root/` governed by a frozen manifest JSON file."""

    def __init__(self, root: str | Path, manifest_path: str | Path) -> None:
        self._root = Path(root)
        self._manifest_path = Path(manifest_path)
        self._entries: dict[str, ManifestEntry] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        with self._manifest_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        for record in raw:
            entry = ManifestEntry(**record)
            self._entries[entry.source_id] = entry
        self._loaded = True

    def list_manifest(self) -> list[ManifestEntry]:
        self._load()
        return sorted(self._entries.values(), key=lambda entry: entry.source_id)

    def open_item(self, source_id: str) -> bytes:
        self._load()
        entry = self._entries.get(source_id)
        if entry is None:
            raise KeyError(f"source_id not in manifest: {source_id}")
        item_path = self._root / entry.path
        with item_path.open("rb") as handle:  # read-only
            return handle.read()

    def open_stream(
        self, source_id: str, chunk_size: int = 1 << 20
    ) -> Iterator[bytes]:
        self._load()
        entry = self._entries.get(source_id)
        if entry is None:
            raise KeyError(f"source_id not in manifest: {source_id}")
        item_path = self._root / entry.path
        with item_path.open("rb") as handle:  # read-only
            while chunk := handle.read(chunk_size):
                yield chunk
