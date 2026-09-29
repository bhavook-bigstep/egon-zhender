"""Stage 6 — Score / Band and item summary assembly.

Maps findings to bands and assembles the one-row-per-item summary. Deterministic
findings are reported as facts (band DETERMINISTIC, no score); AI findings carry a
score, band, and calibration status (Contract 3). Thresholds come from config, never
literals (`.claude/rules/matching-scoring.md`).
"""

from __future__ import annotations

from libs.calibration import Calibrator
from libs.schemas import (
    Band,
    CalibrationStatus,
    ExceptionCode,
    Finding,
    FlagStatus,
    ManifestEntry,
    ProcessingStatus,
    ScoreType,
    ScoringConfig,
    Ws1Summary,
)

_SCORED_TYPES = (ScoreType.MODEL_SCORE, ScoreType.CLASSIFIER_SCORE)


def band_for(score: float, cfg: ScoringConfig) -> Band:
    """Map a 0-100 score to a band using configured thresholds."""
    if score >= cfg.band_high:
        return Band.HIGH
    if score >= cfg.band_medium:
        return Band.MEDIUM
    return Band.LOW


def finalize_scored(
    findings: list[Finding],
    scoring: ScoringConfig,
    calibrator: Calibrator,
) -> list[Finding]:
    """Apply calibration to AI/probabilistic findings and assign their band.

    Deterministic and SIMILARITY findings pass through unchanged.
    """
    finalized: list[Finding] = []
    for finding in findings:
        if finding.score_type in _SCORED_TYPES and finding.score is not None:
            score, status = calibrator.apply(finding.category, finding.score)
            finalized.append(
                finding.model_copy(
                    update={
                        "score": score,
                        "calibration_status": status,
                        "band": band_for(score, scoring),
                    }
                )
            )
        else:
            finalized.append(finding)
    return finalized


def _reason_summary(findings: list[Finding]) -> str:
    parts: list[str] = []
    for finding in sorted(findings, key=lambda item: (item.category, item.finding_id)):
        if finding.score is None:
            # Deterministic: cite the rule ID so the summary row is self-explanatory
            # without a join to the findings file (Contract 3).
            label = finding.rule_id or finding.score_type.value
            parts.append(f"{finding.category}:{label}")
        else:
            parts.append(
                f"{finding.category}:{finding.score_type.value}({finding.score:.0f})"
            )
    return "; ".join(parts)


def summarise(
    entry: ManifestEntry,
    findings: list[Finding],
    exception_code: ExceptionCode | None,
    coverage_complete: bool,
    cfg: ScoringConfig,
    run_id: str,
    config_version: str,
    snapshot_id: str,
) -> Ws1Summary:
    """Assemble the WS-1 summary row for one item."""
    # SIMILARITY findings are routing signals, not flags — exclude from the decision.
    flagging = [
        finding for finding in findings if finding.score_type is not ScoreType.SIMILARITY
    ]

    if exception_code is not None and not flagging:
        flag_status = FlagStatus.UNABLE_TO_PROCESS
    elif flagging:
        flag_status = FlagStatus.FLAGGED
    else:
        flag_status = FlagStatus.NOT_FLAGGED

    processing_status = (
        ProcessingStatus.COMPLETE
        if exception_code is None and coverage_complete
        else ProcessingStatus.PARTIAL
    )

    deterministic = [
        finding
        for finding in flagging
        if finding.score_type is ScoreType.DETERMINISTIC_MATCH
    ]
    strongest_band: Band | None = None
    strongest_score_type: ScoreType | None = None
    strongest_score: float | None = None
    calibration_status = CalibrationStatus.NOT_APPLICABLE

    if deterministic:
        strongest_band = Band.DETERMINISTIC
        strongest_score_type = ScoreType.DETERMINISTIC_MATCH
    elif flagging:
        top = max(flagging, key=lambda finding: finding.score or 0.0)
        strongest_band = top.band
        strongest_score_type = top.score_type
        strongest_score = top.score
        calibration_status = top.calibration_status

    if flag_status is FlagStatus.UNABLE_TO_PROCESS:
        reason_summary = (
            f"unable to process ({exception_code.value})"
            if exception_code is not None
            else "unable to process"
        )
    elif flagging:
        reason_summary = _reason_summary(flagging)
    else:
        reason_summary = "no finding above threshold"

    categories = sorted({finding.category for finding in flagging})

    return Ws1Summary(
        source_id=entry.source_id,
        snapshot_id=snapshot_id,
        content_type=entry.content_type,
        flag_status=flag_status,
        sensitivity_categories=categories,
        reason_summary=reason_summary,
        processing_status=processing_status,
        calibration_status=calibration_status,
        content_hash=entry.content_hash,
        run_id=run_id,
        config_version=config_version,
        author=entry.author,
        datetime=entry.datetime,
        linked_executive=entry.linked_executive,
        linked_project=entry.linked_project,
        strongest_band=strongest_band,
        strongest_score_type=strongest_score_type,
        strongest_score=strongest_score,
        exception_code=exception_code,
    )
