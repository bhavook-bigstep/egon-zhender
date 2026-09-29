"""SourceReader port (Part 1).

Read-only by construction: the protocol exposes no write/redact/merge/overwrite
method, so no adapter can mutate a source record (Contract 1). Later a
`DatabricksReader` implements the same protocol and drops in via config.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from libs.schemas import ManifestEntry


@runtime_checkable
class SourceReader(Protocol):
    """A read-only view over an authorised, frozen set of source items."""

    def list_manifest(self) -> list[ManifestEntry]:
        """Return the frozen manifest of authorised source items."""
        ...

    def open_item(self, source_id: str) -> bytes:
        """Return the raw bytes of one authorised item, read-only.

        Convenience over small items. For large documents (production corpus is
        ~55 GB) prefer `open_stream` so an adapter never materialises a whole file.
        """
        ...

    def open_stream(self, source_id: str) -> Iterator[bytes]:
        """Yield the item's bytes in bounded chunks, read-only (streaming path)."""
        ...
