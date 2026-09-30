"""RegexEngine — deterministic regex recognisers (skeleton default).

Config-driven recognisers matching tokens in the text. Two sources, both scanned over
the full extracted text:

  * `detect.recognisers` — the `{rule_id, category, pattern}` list (the synthetic sample
    tokens), each hit → a deterministic finding citing its rule ID.
  * `detect.custom_recognizers` — the operator-defined recognisers added via the admin UI
    (or config). WITHOUT a Presidio container these would otherwise silently do nothing;
    honouring them here means a checksum-validated recogniser (incl. `weighted_modulus`)
    works under the default engine too. A checksum PASS keeps the match (deterministic),
    a FAIL drops it. The matched value is used transiently for the checksum only — never
    logged (Contract 2).

Each hit cites its rule ID and evidence location — never the matched string (Contract 3).
"""

from __future__ import annotations

import logging
import re

from libs.checksums import resolve_validator
from libs.schemas import (
    Band,
    CalibrationStatus,
    CustomRecogniserConfig,
    DetectConfig,
    Finding,
    ScoreType,
)
from pipelines.workstream1_sensitive.extract import ExtractedText, resolve_location

_DETECTOR_VERSION = "detect-regex-0.1"
logger = logging.getLogger("ws1.detect")


class RegexEngine:
    def __init__(self, cfg: DetectConfig) -> None:
        self._recognisers = cfg.recognisers
        self._custom = cfg.custom_recognizers
        self._category_map = cfg.category_map
        # entities detected but not mapped to a taxonomy category (best-effort, last analyze).
        self.unmapped_entities: dict[str, int] = {}

    def analyze(self, extracted: ExtractedText) -> list[Finding]:
        self.unmapped_entities = {}
        findings: list[Finding] = []
        for recogniser in self._recognisers:
            pattern = re.compile(recogniser.pattern)
            for index, match in enumerate(pattern.finditer(extracted.text)):
                findings.append(
                    Finding(
                        source_id=extracted.source_id,
                        finding_id=f"{recogniser.rule_id}-{index}",
                        category=recogniser.category,
                        reason_code=recogniser.reason_code,
                        reason_text=f"rule {recogniser.rule_id} matched",
                        score_type=ScoreType.DETERMINISTIC_MATCH,
                        band=Band.DETERMINISTIC,
                        calibration_status=CalibrationStatus.NOT_APPLICABLE,
                        evidence_location=resolve_location(
                            match.start(), match.end(), extracted.spans
                        ),
                        detector_version=_DETECTOR_VERSION,
                        rule_id=recogniser.rule_id,
                        score=None,
                    )
                )
        for custom in self._custom:
            findings.extend(self._custom_findings(custom, extracted))
        if self.unmapped_entities:  # detected but unmapped → visible, not a silent drop
            logger.warning(
                "detect: %d custom recogniser hit(s) unmapped to a taxonomy category: %s",
                sum(self.unmapped_entities.values()),
                dict(sorted(self.unmapped_entities.items())),
            )
        return findings

    def _custom_findings(
        self, recogniser: CustomRecogniserConfig, extracted: ExtractedText
    ) -> list[Finding]:
        entity = recogniser.supported_entity
        category = self._category_map.get(entity)
        if category is None:  # not in the taxonomy mapping — surface it, do not silently drop
            self.unmapped_entities[entity] = self.unmapped_entities.get(entity, 0) + 1
            return []
        validator = resolve_validator(recogniser.validator, recogniser.checksum)
        out: list[Finding] = []
        seen: set[tuple[int, int]] = set()  # de-dupe overlapping patterns on the same span
        for pattern_spec in recogniser.patterns:
            pattern = re.compile(pattern_spec.regex)
            for match in pattern.finditer(extracted.text):
                key = (match.start(), match.end())
                if key in seen:
                    continue
                if validator is not None and not validator.check(match.group()):
                    continue  # checksum failed → not a real identifier, drop it
                seen.add(key)
                label = f"{entity}:{validator.name}" if validator else entity
                reason = (
                    f"{entity} passed {validator.name} checksum"
                    if validator
                    else f"custom recogniser {recogniser.name} matched"
                )
                out.append(
                    Finding(
                        source_id=extracted.source_id,
                        finding_id=f"{recogniser.name}-{len(out)}",
                        category=category,
                        reason_code="custom_checksum" if validator else "custom_regex",
                        reason_text=reason,
                        score_type=ScoreType.DETERMINISTIC_MATCH,
                        band=Band.DETERMINISTIC,
                        calibration_status=CalibrationStatus.NOT_APPLICABLE,
                        evidence_location=resolve_location(
                            match.start(), match.end(), extracted.spans
                        ),
                        detector_version=_DETECTOR_VERSION,
                        rule_id=label,
                        score=None,
                    )
                )
        return out
