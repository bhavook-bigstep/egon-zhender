"""finalize_scored (calibration + band) and SIMILARITY exclusion from flagging."""

from __future__ import annotations

from libs.calibration import Calibrator
from libs.schemas import (
    Band,
    CalibrationStatus,
    EvidenceLocation,
    Finding,
    FlagStatus,
    ManifestEntry,
    ScoreType,
    ScoringConfig,
)
from pipelines.workstream1_sensitive.score import finalize_scored, summarise

ENTRY = ManifestEntry(source_id="x", content_type="text/plain", content_hash="h", path="p")
SCORING = ScoringConfig()


def _model_finding(score: float) -> Finding:
    return Finding(
        source_id="x",
        finding_id="model-financial",
        category="financial",
        reason_code="model_flag",
        reason_text="model score",
        score_type=ScoreType.MODEL_SCORE,
        band=None,
        calibration_status=CalibrationStatus.NOT_CALIBRATED,
        evidence_location=EvidenceLocation(),
        detector_version="mock",
        score=score,
    )


def _similarity_finding() -> Finding:
    return Finding(
        source_id="x",
        finding_id="semantic-financial",
        category="financial",
        reason_code="semantic_route",
        reason_text="cosine",
        score_type=ScoreType.SIMILARITY,
        band=None,
        calibration_status=CalibrationStatus.NOT_APPLICABLE,
        evidence_location=EvidenceLocation(),
        detector_version="semantic-0.1",
        score=0.9,
    )


def test_finalize_sets_band_and_calibration() -> None:
    out = finalize_scored([_model_finding(90)], SCORING, Calibrator.empty())
    assert out[0].band is Band.HIGH
    assert out[0].calibration_status is CalibrationStatus.NOT_CALIBRATED
    assert out[0].score == 90.0


def test_finalize_passes_similarity_through_untouched() -> None:
    out = finalize_scored([_similarity_finding()], SCORING, Calibrator.empty())
    assert out[0].band is None
    assert out[0].score == 0.9


def test_similarity_alone_does_not_flag() -> None:
    summary = summarise(
        ENTRY, [_similarity_finding()], None, True, SCORING, "run", "cfg", "snap"
    )
    assert summary.flag_status is FlagStatus.NOT_FLAGGED
    assert summary.sensitivity_categories == []


def test_model_finding_flags_over_similarity() -> None:
    findings = finalize_scored([_model_finding(90)], SCORING, Calibrator.empty())
    findings.append(_similarity_finding())
    summary = summarise(ENTRY, findings, None, True, SCORING, "run", "cfg", "snap")
    assert summary.flag_status is FlagStatus.FLAGGED
    assert summary.sensitivity_categories == ["financial"]
    assert summary.strongest_score_type is ScoreType.MODEL_SCORE
