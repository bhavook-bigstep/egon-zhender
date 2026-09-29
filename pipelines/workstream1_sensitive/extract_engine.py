"""Extraction-engine port + factory.

`ExtractionEngine` is the swappable interface for Stage 2. `DecodeExtractor` (skeleton)
and `NativeExtractor` (real born-digital) are wired now; the Docling/Tika HTTP adapters
are added with their containers in later waves.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from libs.schemas import ExtractConfig, ManifestEntry
from pipelines.workstream1_sensitive.extract import ExtractedText


@runtime_checkable
class ExtractionEngine(Protocol):
    def extract(self, entry: ManifestEntry, data: bytes) -> ExtractedText:
        """Return the extraction result for one item (never modifies the source)."""
        ...


def build_extraction_engine(cfg: ExtractConfig) -> ExtractionEngine:
    """Construct the extraction engine named by config."""
    if cfg.engine == "decode":
        from pipelines.workstream1_sensitive.extract import DecodeExtractor

        return DecodeExtractor()
    if cfg.engine == "native":
        from pipelines.workstream1_sensitive.extract_native import NativeExtractor

        return NativeExtractor()
    if cfg.engine == "docling":
        from pipelines.workstream1_sensitive.extract_docling import DoclingHttpExtractor

        if not cfg.docling_url:
            raise ValueError("docling engine requires extract.docling_url")
        return DoclingHttpExtractor(cfg.docling_url)
    if cfg.engine == "tika":
        from pipelines.workstream1_sensitive.extract_tika import TikaHttpExtractor

        if not cfg.tika_url:
            raise ValueError("tika engine requires extract.tika_url")
        return TikaHttpExtractor(cfg.tika_url)
    raise ValueError(f"unsupported extraction engine: {cfg.engine}")
