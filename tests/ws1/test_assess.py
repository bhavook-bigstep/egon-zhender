"""Assess stage: routing over categories, raw scores, minimal span, egress flag."""

from __future__ import annotations

from libs.inference.base import InferenceRequest, InferenceResult
from libs.inference.mock import MockProvider
from libs.schemas import CalibrationStatus, ScoreType, ScoringConfig
from pipelines.workstream1_sensitive.assess import assess
from pipelines.workstream1_sensitive.extract import ExtractedText

CATEGORIES = ["financial", "health"]
SCORING = ScoringConfig()


def _extracted(text: str) -> ExtractedText:
    return ExtractedText(source_id="x", text=text)


def test_assess_flags_on_hint_raw_unbanded() -> None:
    provider = MockProvider("mock-0", False, {"financial": "salary", "health": "diagnosis"})
    findings = assess(_extracted("the salary review memo"), CATEGORIES, SCORING, provider)
    assert {f.category for f in findings} == {"financial"}
    finding = findings[0]
    assert finding.score_type is ScoreType.MODEL_SCORE
    assert finding.score == 90.0
    assert finding.band is None  # band assigned later, in finalize_scored
    assert finding.calibration_status is CalibrationStatus.NOT_CALIBRATED


def test_assess_no_hint_no_finding() -> None:
    provider = MockProvider("mock-0", False, {"financial": "salary"})
    assert assess(_extracted("entirely benign text"), CATEGORIES, SCORING, provider) == []


class _SpyProvider:
    def __init__(self, score: float) -> None:
        self.score = score
        self.calls = 0
        self.last_crosses: bool | None = None
        self._is_local = True

    @property
    def is_local(self) -> bool:
        return self._is_local

    def assess(self, request: InferenceRequest) -> InferenceResult:
        self.calls += 1
        self.last_crosses = request.crosses_boundary
        return InferenceResult(score=self.score, model_version="spy")


def test_assess_sends_minimal_span() -> None:
    class _Capture(_SpyProvider):
        def assess(self, request: InferenceRequest) -> InferenceResult:
            assert len(request.text) <= 512
            return super().assess(request)

    capture = _Capture(5.0)
    assess(_extracted("x" * 2000), ["financial"], SCORING, capture)
    assert capture.calls == 1


def test_assess_empty_text_never_calls_provider() -> None:
    provider = _SpyProvider(90.0)
    assert assess(_extracted("   \n  "), CATEGORIES, SCORING, provider) == []
    assert provider.calls == 0


def test_assess_flag_threshold_is_inclusive() -> None:
    provider = _SpyProvider(SCORING.flag_threshold)
    findings = assess(_extracted("anything"), ["financial"], SCORING, provider)
    assert len(findings) == 1


def test_assess_just_below_threshold_no_finding() -> None:
    provider = _SpyProvider(SCORING.flag_threshold - 0.01)
    assert assess(_extracted("anything"), ["financial"], SCORING, provider) == []


def test_assess_egress_flag_derived_from_provider(monkeypatch) -> None:
    local = _SpyProvider(90.0)
    local._is_local = True
    assess(_extracted("anything"), ["financial"], SCORING, local)
    assert local.last_crosses is False

    # Remote provider crosses the boundary → masking runs, so a key must be available.
    monkeypatch.setenv("WS1_TEST_HASH_KEY", "secret")
    remote = _SpyProvider(90.0)
    remote._is_local = False
    assess(_extracted("anything"), ["financial"], SCORING, remote, "WS1_TEST_HASH_KEY")
    assert remote.last_crosses is True
