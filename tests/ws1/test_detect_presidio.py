"""PresidioEngine mapping (fake analyzer — no Presidio/spaCy install needed)."""

from __future__ import annotations

from dataclasses import dataclass

from libs.schemas import DetectConfig, ScoreType
from pipelines.workstream1_sensitive.detect_presidio import PresidioEngine
from pipelines.workstream1_sensitive.extract import ExtractedText


@dataclass
class _FakeResult:
    entity_type: str
    start: int
    end: int
    score: float


class _FakeAnalyzer:
    def __init__(self, results: list[_FakeResult]) -> None:
        self._results = results

    def analyze(self, text: str, language: str, score_threshold: float):  # noqa: ANN201
        return self._results


CFG = DetectConfig(
    engine="presidio",
    category_map={"CREDIT_CARD": "financial", "PERSON": "health"},
    deterministic_entities=["CREDIT_CARD"],
)


def _extracted(text: str) -> ExtractedText:
    return ExtractedText(source_id="x", text=text, has_text_layer=True)


def test_deterministic_entity_maps_to_deterministic_match() -> None:
    engine = PresidioEngine(CFG, analyzer=_FakeAnalyzer([_FakeResult("CREDIT_CARD", 5, 20, 0.95)]))
    finding = engine.analyze(_extracted("card 4111111111111111 here"))[0]
    assert finding.score_type is ScoreType.DETERMINISTIC_MATCH
    assert finding.score is None
    assert finding.rule_id == "CREDIT_CARD"
    assert finding.category == "financial"


def test_ner_entity_maps_to_classifier_score() -> None:
    engine = PresidioEngine(CFG, analyzer=_FakeAnalyzer([_FakeResult("PERSON", 0, 4, 0.8)]))
    finding = engine.analyze(_extracted("Jane and others"))[0]
    assert finding.score_type is ScoreType.CLASSIFIER_SCORE
    assert finding.score == 80.0
    assert finding.band is None  # assigned after calibration
    assert finding.category == "health"


def test_unmapped_entity_is_skipped() -> None:
    engine = PresidioEngine(CFG, analyzer=_FakeAnalyzer([_FakeResult("URL", 0, 3, 0.9)]))
    assert engine.analyze(_extracted("http://x")) == []
