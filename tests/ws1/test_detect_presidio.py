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


def test_unmapped_entity_is_skipped_but_counted() -> None:
    engine = PresidioEngine(CFG, analyzer=_FakeAnalyzer([_FakeResult("URL", 0, 3, 0.9)]))
    assert engine.analyze(_extracted("http://x")) == []
    assert engine.unmapped_entities == {"URL": 1}  # visible, not a silent drop


def test_contact_identifier_mapping() -> None:
    # EMAIL_ADDRESS / PHONE_NUMBER map to the contact_identifier category (Presidio catches
    # them at the detect stage — no LLM routing needed).
    cfg = DetectConfig(
        engine="presidio",
        category_map={"EMAIL_ADDRESS": "contact_identifier", "PHONE_NUMBER": "contact_identifier"},
    )
    engine = PresidioEngine(
        cfg, analyzer=_FakeAnalyzer([_FakeResult("EMAIL_ADDRESS", 5, 20, 0.99)])
    )
    finding = engine.analyze(_extracted("mail jane@example.com now"))[0]
    assert finding.category == "contact_identifier"
    assert finding.score == 99.0
    assert engine.unmapped_entities == {}


def test_checksum_validator_passes_and_fails() -> None:
    """A custom recogniser with a checksum validator: pass → deterministic, fail → dropped."""
    from libs.schemas import CustomRecogniserConfig, PatternSpec
    from pipelines.workstream1_sensitive.detect_presidio import (
        map_presidio_results,
        validators_for,
    )

    cfg = DetectConfig(
        engine="presidio",
        category_map={"CARD": "financial"},
        custom_recognizers=[
            CustomRecogniserConfig(
                name="card",
                supported_entity="CARD",
                patterns=[PatternSpec(name="card", regex=r"\d{16}", score=0.5)],
                validator="luhn",
            )
        ],
    )
    text = "pay 4111111111111111 or 4111111111111112 today"  # first valid Luhn, second not
    results = [
        _FakeResult("CARD", 4, 20, 0.5),   # 4111111111111111 → valid
        _FakeResult("CARD", 24, 40, 0.5),  # 4111111111111112 → invalid checksum → dropped
    ]
    findings = map_presidio_results(
        results, cfg, "x", [], text=text, validators=validators_for(cfg)
    )
    assert len(findings) == 1
    assert findings[0].score_type is ScoreType.DETERMINISTIC_MATCH
    assert findings[0].rule_id == "CARD:luhn"
    assert findings[0].score is None


def test_weighted_modulus_validator_gates_matches() -> None:
    """A weighted_modulus (declarative) checksum drops the routing number that fails it."""
    from libs.schemas import ChecksumSpec, CustomRecogniserConfig, PatternSpec
    from pipelines.workstream1_sensitive.detect_presidio import (
        map_presidio_results,
        validators_for,
    )

    cfg = DetectConfig(
        engine="presidio",
        category_map={"ABA": "financial"},
        custom_recognizers=[
            CustomRecogniserConfig(
                name="aba",
                supported_entity="ABA",
                patterns=[PatternSpec(name="aba", regex=r"\d{9}", score=0.5)],
                validator="weighted_modulus",
                checksum=ChecksumSpec(modulus=10, weights=[3, 7, 1], align="left"),
            )
        ],
    )
    text = "routing 011000015 vs 011000016"  # first valid ABA, second not
    results = [_FakeResult("ABA", 8, 17, 0.5), _FakeResult("ABA", 21, 30, 0.5)]
    findings = map_presidio_results(
        results, cfg, "x", [], text=text, validators=validators_for(cfg)
    )
    assert len(findings) == 1
    assert findings[0].score_type is ScoreType.DETERMINISTIC_MATCH
    assert findings[0].rule_id == "ABA:weighted_modulus"
