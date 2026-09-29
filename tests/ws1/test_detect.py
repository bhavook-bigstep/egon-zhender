"""RegexEngine detection: hits/misses, evidence by location, content-free findings."""

from __future__ import annotations

import pytest

from libs.schemas import DetectConfig, EvidenceLocation, RecogniserConfig, ScoreType
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


def _extracted(text: str) -> ExtractedText:
    return decode_text("x", text.encode("utf-8"))


def test_detect_hit_cites_rule_and_location() -> None:
    engine = RegexEngine(RECOGNISERS)
    findings = engine.analyze(_extracted("ref ACCT-123456 end"))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "FIN-001"
    assert finding.score_type is ScoreType.DETERMINISTIC_MATCH
    assert finding.score is None
    assert finding.evidence_location.char_start is not None
    assert "ACCT-123456" not in finding.reason_text  # content-free


def test_detect_multiple_hits_distinct_ids() -> None:
    engine = RegexEngine(RECOGNISERS)
    findings = engine.analyze(_extracted("ACCT-111111 and ACCT-222222"))
    assert [f.finding_id for f in findings] == ["FIN-001-0", "FIN-001-1"]


def test_detect_miss_returns_empty() -> None:
    engine = RegexEngine(RECOGNISERS)
    assert engine.analyze(_extracted("nothing to see here")) == []


def test_detect_resolves_page_location_from_spans() -> None:
    # A PDF-style span carrying a page anchor → finding cites the page, not a char offset.
    spans = [(EvidenceLocation(page=7), "ref ACCT-123456 end")]
    extracted = ExtractedText(
        source_id="x", text="ref ACCT-123456 end", spans=spans, has_text_layer=True
    )
    finding = RegexEngine(RECOGNISERS).analyze(extracted)[0]
    assert finding.evidence_location.page == 7


def test_factory_selects_regex() -> None:
    engine = build_detection_engine(DetectConfig(engine="regex", recognisers=RECOGNISERS))
    assert isinstance(engine, RegexEngine)


def test_factory_unknown_engine_raises() -> None:
    with pytest.raises(ValueError):
        build_detection_engine(DetectConfig(engine="nope"))
