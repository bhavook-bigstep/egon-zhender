"""Stage 4 — Detect: the detection-engine port + factory.

`DetectionEngine` is the swappable interface; `RegexEngine` (deterministic regex
recognisers, the skeleton default) and `PresidioEngine` (Presidio recognisers, Phase 2)
implement it, selected by `detect.engine` in config. Findings are content-free
(evidence by location only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from libs.schemas import DetectConfig, Finding

if TYPE_CHECKING:
    from pipelines.workstream1_sensitive.extract import ExtractedText


@runtime_checkable
class DetectionEngine(Protocol):
    def analyze(self, extracted: ExtractedText) -> list[Finding]:
        """Return findings for all recogniser hits, anchored to span locations."""
        ...


def build_detection_engine(cfg: DetectConfig) -> DetectionEngine:
    """Construct the detection engine named by config (heavy engine lazy-imported)."""
    if cfg.engine == "regex":
        from pipelines.workstream1_sensitive.detect_regex import RegexEngine

        return RegexEngine(cfg.recognisers)
    if cfg.engine == "presidio":
        from pipelines.workstream1_sensitive.detect_presidio import PresidioEngine

        return PresidioEngine(cfg)
    if cfg.engine == "presidio_http":
        from pipelines.workstream1_sensitive.detect_presidio_http import (
            PresidioHttpEngine,
        )

        return PresidioHttpEngine(cfg)
    raise ValueError(f"unsupported detection engine: {cfg.engine}")
