"""RegexEngine detection: hits/misses, evidence by location, content-free findings."""

from __future__ import annotations

import pytest

from libs.schemas import (
    ChecksumSpec,
    CustomRecogniserConfig,
    DetectConfig,
    EvidenceLocation,
    PatternSpec,
    RecogniserConfig,
    ScoreType,
)
from pipelines.workstream1_sensitive.detect import build_detection_engine
from pipelines.workstream1_sensitive.detect_regex import RegexEngine
from pipelines.workstream1_sensitive.extract import ExtractedText, decode_text

RECOGNISERS = [
    RecogniserConfig(
        rule_id="FIN-001",
        category="financial",
        pattern=r"ACCT-\d{6}",
        reason_code="financial_account_ref",
    )
]


def _engine(**kw: object) -> RegexEngine:
    return RegexEngine(DetectConfig(engine="regex", recognisers=RECOGNISERS, **kw))  # type: ignore[arg-type]


def _extracted(text: str) -> ExtractedText:
    return decode_text("x", text.encode("utf-8"))


def test_detect_hit_cites_rule_and_location() -> None:
    findings = _engine().analyze(_extracted("ref ACCT-123456 end"))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "FIN-001"
    assert finding.score_type is ScoreType.DETERMINISTIC_MATCH
    assert finding.score is None
    assert finding.evidence_location.char_start is not None
    assert "ACCT-123456" not in finding.reason_text  # content-free


def test_detect_multiple_hits_distinct_ids() -> None:
    findings = _engine().analyze(_extracted("ACCT-111111 and ACCT-222222"))
    assert [f.finding_id for f in findings] == ["FIN-001-0", "FIN-001-1"]


def test_detect_miss_returns_empty() -> None:
    assert _engine().analyze(_extracted("nothing to see here")) == []


def test_detect_resolves_page_location_from_spans() -> None:
    # A PDF-style span carrying a page anchor → finding cites the page, not a char offset.
    spans = [(EvidenceLocation(page=7), "ref ACCT-123456 end")]
    extracted = ExtractedText(
        source_id="x", text="ref ACCT-123456 end", spans=spans, has_text_layer=True
    )
    finding = _engine().analyze(extracted)[0]
    assert finding.evidence_location.page == 7


def test_regex_engine_honours_custom_checksum_recogniser() -> None:
    """A custom weighted_modulus recogniser works under the default engine too (no Presidio):
    a checksum PASS is kept as deterministic, a FAIL is dropped."""
    engine = RegexEngine(
        DetectConfig(
            engine="regex",
            category_map={"ABA_ROUTING": "financial"},
            custom_recognizers=[
                CustomRecogniserConfig(
                    name="aba",
                    supported_entity="ABA_ROUTING",
                    patterns=[PatternSpec(name="aba", regex=r"\b\d{9}\b", score=0.5)],
                    validator="weighted_modulus",
                    checksum=ChecksumSpec(modulus=10, weights=[3, 7, 1], align="left"),
                )
            ],
        )
    )
    findings = engine.analyze(_extracted("routing 011000015 and 011000016"))
    assert len(findings) == 1  # only the checksum-valid one survives
    assert findings[0].rule_id == "ABA_ROUTING:weighted_modulus"
    assert findings[0].score_type is ScoreType.DETERMINISTIC_MATCH
    assert findings[0].category == "financial"


def test_regex_engine_surfaces_unmapped_custom_entity() -> None:
    """A custom entity with no category_map entry is counted, not silently dropped."""
    engine = RegexEngine(
        DetectConfig(
            engine="regex",
            category_map={},  # SWIFT not mapped
            custom_recognizers=[
                CustomRecogniserConfig(
                    name="swift",
                    supported_entity="SWIFT_BIC",
                    patterns=[PatternSpec(name="swift", regex=r"[A-Z]{6}[A-Z0-9]{2}", score=0.5)],
                )
            ],
        )
    )
    assert engine.analyze(_extracted("bic DEUTDEFF here")) == []
    assert engine.unmapped_entities == {"SWIFT_BIC": 1}


def test_factory_selects_regex() -> None:
    engine = build_detection_engine(DetectConfig(engine="regex", recognisers=RECOGNISERS))
    assert isinstance(engine, RegexEngine)


def test_factory_unknown_engine_raises() -> None:
    with pytest.raises(ValueError):
        build_detection_engine(DetectConfig(engine="nope"))
