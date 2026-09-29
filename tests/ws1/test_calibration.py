"""Calibration: §3.3 status rule, mapping application, artefact round-trip + tool."""

from __future__ import annotations

import sys
from pathlib import Path

from libs.calibration import Calibrator, fit_calibrator
from libs.schemas import CalibrationStatus


def _labels(positives: int, negatives: int, holdout: list[list[int]]):
    dev = [[90, 1]] * positives + [[10, 0]] * negatives
    return {"cat": {"dev": dev, "holdout": holdout}}


def test_calibrated_when_enough_positives_and_low_error() -> None:
    labels = _labels(120, 20, holdout=[[90, 1], [10, 0]])
    cal = fit_calibrator(
        labels, "cal-t", method="identity", min_positives=100, max_holdout_error=100
    )
    _, status = cal.apply("cat", 90)
    assert status is CalibrationStatus.CALIBRATED


def test_provisional_when_too_few_positives() -> None:
    labels = _labels(10, 10, holdout=[[90, 1], [10, 0]])
    cal = fit_calibrator(labels, "cal-t", method="identity", min_positives=100)
    _, status = cal.apply("cat", 90)
    assert status is CalibrationStatus.PROVISIONAL


def test_provisional_when_holdout_error_too_high() -> None:
    # Enough positives, but an inverted holdout blows the error budget.
    labels = _labels(120, 0, holdout=[[90, 0], [10, 1]])
    cal = fit_calibrator(
        labels, "cal-t", method="identity", min_positives=100, max_holdout_error=5.0
    )
    _, status = cal.apply("cat", 90)
    assert status is CalibrationStatus.PROVISIONAL


def test_not_calibrated_when_no_positives() -> None:
    labels = {"cat": {"dev": [[10, 0], [5, 0]], "holdout": [[10, 0]]}}
    cal = fit_calibrator(labels, "cal-t", method="identity")
    _, status = cal.apply("cat", 90)
    assert status is CalibrationStatus.NOT_CALIBRATED


def test_apply_unknown_category_is_not_calibrated() -> None:
    cal = Calibrator.empty()
    score, status = cal.apply("nope", 77.0)
    assert score == 77.0
    assert status is CalibrationStatus.NOT_CALIBRATED


def test_artefact_roundtrip(tmp_path: Path) -> None:
    import json

    labels = _labels(3, 1, holdout=[[90, 1]])
    cal = fit_calibrator(labels, "cal-t", method="identity")
    path = tmp_path / "artefact.json"
    path.write_text(json.dumps(cal.to_dict()), encoding="utf-8")
    loaded = Calibrator.load(path)
    assert loaded.version == "cal-t"
    assert loaded.apply("cat", 90)[1] is CalibrationStatus.PROVISIONAL


def test_calibrate_tool_writes_artefact(tmp_path: Path, monkeypatch) -> None:
    from pipelines.workstream1_sensitive.calibrate import main

    out = tmp_path / "artefact.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "calibrate",
            "--labels",
            "tests/fixtures/ws1_calibration_labels.json",
            "--out",
            str(out),
            "--method",
            "identity",
        ],
    )
    assert main() == 0
    cal = Calibrator.load(out)
    # 'health' has no positives in the fixture → NOT_CALIBRATED.
    assert cal.apply("health", 50)[1] is CalibrationStatus.NOT_CALIBRATED
