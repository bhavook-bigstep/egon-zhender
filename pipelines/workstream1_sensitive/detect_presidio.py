"""PresidioEngine — Presidio recognisers mapped to WS-1 findings (Phase 2).

Checksum/validated entities (declared in `detect.deterministic_entities`) become
DETERMINISTIC_MATCH findings citing the entity as rule_id (no numeric score). Other
(NER/context) entities become CLASSIFIER_SCORE findings carrying Presidio's confidence
(0-100); their band + calibration status are assigned centrally after calibration.
Entity types map to taxonomy categories via `detect.category_map`.

The Presidio `AnalyzerEngine` is lazy-imported and injectable, so unit tests exercise
the mapping with a fake analyzer and need no Presidio/spaCy install.
"""

from __future__ import annotations

from typing import Any

from libs.schemas import (
    Band,
    CalibrationStatus,
    DetectConfig,
    EvidenceLocation,
    Finding,
    ScoreType,
)
from pipelines.workstream1_sensitive.extract import ExtractedText, resolve_location


def map_presidio_results(
    results: Any,
    cfg: DetectConfig,
    source_id: str,
    spans: list[tuple[EvidenceLocation, str]],
) -> list[Finding]:
    """Map Presidio recogniser results (objects with entity_type/start/end/score) to
    findings, anchoring each to its span location. Shared by both Presidio engines.
    """
    findings: list[Finding] = []
    for index, result in enumerate(results):
        entity = result.entity_type
        category = cfg.category_map.get(entity)
        if category is None:
            continue  # entity not in the approved taxonomy mapping
        location = resolve_location(result.start, result.end, spans)
        if entity in cfg.deterministic_entities:
            findings.append(
                Finding(
                    source_id=source_id,
                    finding_id=f"{entity}-{index}",
                    category=category,
                    reason_code="presidio_deterministic",
                    reason_text=f"validated entity {entity}",
                    score_type=ScoreType.DETERMINISTIC_MATCH,
                    band=Band.DETERMINISTIC,
                    calibration_status=CalibrationStatus.NOT_APPLICABLE,
                    evidence_location=location,
                    detector_version=cfg.detector_version,
                    rule_id=entity,
                    score=None,
                )
            )
        else:
            findings.append(
                Finding(
                    source_id=source_id,
                    finding_id=f"{entity}-{index}",
                    category=category,
                    reason_code="presidio_classifier",
                    reason_text=f"recogniser {entity} matched",
                    score_type=ScoreType.CLASSIFIER_SCORE,
                    band=None,  # assigned after calibration
                    calibration_status=CalibrationStatus.NOT_CALIBRATED,
                    evidence_location=location,
                    detector_version=cfg.detector_version,
                    rule_id=entity,
                    score=float(result.score) * 100.0,
                )
            )
    return findings


class PresidioEngine:
    def __init__(self, cfg: DetectConfig, analyzer: Any | None = None) -> None:
        self._cfg = cfg
        self._analyzer = analyzer if analyzer is not None else self._build_analyzer()

    def _build_analyzer(self) -> Any:
        from presidio_analyzer import AnalyzerEngine  # lazy: heavy dependency

        return AnalyzerEngine()

    def analyze(self, extracted: ExtractedText) -> list[Finding]:
        results = self._analyzer.analyze(
            text=extracted.text,
            language=self._cfg.presidio_language,
            score_threshold=self._cfg.presidio_score_threshold,
        )
        return map_presidio_results(
            results, self._cfg, extracted.source_id, extracted.spans
        )
