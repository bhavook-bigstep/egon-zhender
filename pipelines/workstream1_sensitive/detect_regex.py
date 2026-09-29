"""RegexEngine — deterministic regex recognisers (skeleton default).

Config-driven recognisers matching synthetic tokens in the sample. Each hit yields a
deterministic finding citing its rule ID and evidence location — never the matched
string (Contract 3 / privacy rules).
"""

from __future__ import annotations

import re

from libs.schemas import (
    Band,
    CalibrationStatus,
    Finding,
    RecogniserConfig,
    ScoreType,
)
from pipelines.workstream1_sensitive.extract import ExtractedText, resolve_location

_DETECTOR_VERSION = "detect-regex-0.1"


class RegexEngine:
    def __init__(self, recognisers: list[RecogniserConfig]) -> None:
        self._recognisers = recognisers

    def analyze(self, extracted: ExtractedText) -> list[Finding]:
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
        return findings
