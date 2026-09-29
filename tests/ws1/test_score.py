"""Score stage: band thresholds and summary/flag-status logic."""

from __future__ import annotations

from libs.schemas import (
    Band,
    CalibrationStatus,
    EvidenceLocation,
    ExceptionCode,
    Finding,
    FlagStatus,
    ManifestEntry,
    ProcessingStatus,
    ScoreType,
    ScoringConfig,
)
from pipelines.workstream1_sensitive.score import band_for, summarise

ENTRY = ManifestEntry(
    source_id="x", content_type="text/plain", content_hash="h", path="p"
)
SCORING = ScoringConfig()


def test_band_for_boundaries() -> None:
    assert band_for(80.0, SCORING) is Band.HIGH
    assert band_for(79.9, SCORING) is Band.MEDIUM
    assert band_for(60.0, SCORING) is Band.MEDIUM
    assert band_for(59.9, SCORING) is Band.LOW
    assert band_for(40.0, SCORING) is Band.LOW


def _det_finding() -> Finding:
    return Finding(
        source_id="x",
        finding_id="d",
        category="financial",
        reason_code="rc",
        reason_text="rule matched",
        score_type=ScoreType.DETERMINISTIC_MATCH,
        band=Band.DETERMINISTIC,
        calibration_status=CalibrationStatus.NOT_APPLICABLE,
        evidence_location=EvidenceLocation(),
        detector_version="d",
    )


def _model_finding(score: float) -> Finding:
    return Finding(
        source_id="x",
        finding_id="m",
        category="health",
        reason_code="model_flag",
        reason_text="model score",
        score_type=ScoreType.MODEL_SCORE,
        band=Band.HIGH,
        calibration_status=CalibrationStatus.NOT_CALIBRATED,
        evidence_location=EvidenceLocation(),
        detector_version="mock-0",
        score=score,
    )


def _summarise(findings: list[Finding], exception: ExceptionCode | None, coverage: bool):
    return summarise(
        ENTRY, findings, exception, coverage, SCORING, "run", "cfg", "snap"
    )


def test_summarise_deterministic_wins() -> None:
    summary = _summarise([_det_finding(), _model_finding(90)], None, True)
    assert summary.flag_status is FlagStatus.FLAGGED
    assert summary.strongest_band is Band.DETERMINISTIC
    assert summary.strongest_score is None
    assert summary.calibration_status is CalibrationStatus.NOT_APPLICABLE
    assert summary.processing_status is ProcessingStatus.COMPLETE


def test_summarise_model_only() -> None:
    summary = _summarise([_model_finding(82)], None, True)
    assert summary.strongest_score_type is ScoreType.MODEL_SCORE
    assert summary.strongest_score == 82
    assert summary.calibration_status is CalibrationStatus.NOT_CALIBRATED


def test_summarise_not_flagged() -> None:
    summary = _summarise([], None, True)
    assert summary.flag_status is FlagStatus.NOT_FLAGGED
    assert summary.processing_status is ProcessingStatus.COMPLETE


def test_summarise_unable_to_process() -> None:
    summary = _summarise([], ExceptionCode.UNSUPPORTED_TYPE, False)
    assert summary.flag_status is FlagStatus.UNABLE_TO_PROCESS
    assert summary.exception_code is ExceptionCode.UNSUPPORTED_TYPE
    assert summary.processing_status is ProcessingStatus.PARTIAL
