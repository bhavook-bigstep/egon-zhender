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

from libs.checksums import ResolvedValidator, resolve_validator
from libs.schemas import (
    Band,
    CalibrationStatus,
    DetectConfig,
    EvidenceLocation,
    Finding,
    ScoreType,
)
from pipelines.workstream1_sensitive.extract import ExtractedText, resolve_location


def validators_for(cfg: DetectConfig) -> dict[str, ResolvedValidator]:
    """entity_type -> resolved checksum, from the config's custom recognisers. A named
    built-in (luhn/iban_mod97/aba_routing) or the parameterised `weighted_modulus`."""
    resolved: dict[str, ResolvedValidator] = {}
    for rec in cfg.custom_recognizers:
        if not rec.validator:
            continue
        validator = resolve_validator(rec.validator, rec.checksum)
        if validator is not None:
            resolved[rec.supported_entity] = validator
    return resolved


def map_presidio_results(
    results: Any,
    cfg: DetectConfig,
    source_id: str,
    spans: list[tuple[EvidenceLocation, str]],
    *,
    text: str = "",
    validators: dict[str, ResolvedValidator] | None = None,
) -> list[Finding]:
    """Map Presidio recogniser results (objects with entity_type/start/end/score) to
    findings, anchoring each to its span location. Shared by both Presidio engines.

    If an entity has a checksum `validator` configured, the matched substring is verified:
    a PASS becomes a DETERMINISTIC_MATCH; a FAIL drops the finding. The matched value is used
    transiently for the check only — never logged or persisted (Contract 2).
    """
    validators = validators or {}
    findings: list[Finding] = []
    for index, result in enumerate(results):
        entity = result.entity_type
        category = cfg.category_map.get(entity)
        if category is None:
            continue  # entity not in the approved taxonomy mapping
        location = resolve_location(result.start, result.end, spans)
        validator = validators.get(entity)
        if validator is not None:
            if not validator.check(text[result.start : result.end]):
                continue  # checksum failed → not a real identifier, drop it
            findings.append(
                Finding(
                    source_id=source_id,
                    finding_id=f"{entity}-{index}",
                    category=category,
                    reason_code="presidio_checksum",
                    reason_text=f"{entity} passed {validator.name} checksum",
                    score_type=ScoreType.DETERMINISTIC_MATCH,
                    band=Band.DETERMINISTIC,
                    calibration_status=CalibrationStatus.NOT_APPLICABLE,
                    evidence_location=location,
                    detector_version=cfg.detector_version,
                    rule_id=f"{entity}:{validator.name}",
                    score=None,
                )
            )
            continue
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
            results,
            self._cfg,
            extracted.source_id,
            extracted.spans,
            text=extracted.text,
            validators=validators_for(self._cfg),
        )
