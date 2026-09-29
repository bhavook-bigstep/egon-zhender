"""Calibration artefact flows through the full runner onto AI findings."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from libs.calibration import fit_calibrator
from libs.schemas import CalibrationStatus, ScoreType
from pipelines.workstream1_sensitive.runner import run


def test_calibration_status_applied_through_run(tmp_path: Path) -> None:
    # Build an identity calibration artefact where 'financial' has labelled positives
    # (→ PROVISIONAL under the default 100-positive bar).
    labels = {
        "financial": {"dev": [[90, 1], [80, 1], [10, 0]], "holdout": [[90, 1], [10, 0]]}
    }
    calibrator = fit_calibrator(labels, "cal-test", method="identity")
    artefact = tmp_path / "cal.json"
    artefact.write_text(json.dumps(calibrator.to_dict()), encoding="utf-8")

    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    base["scoring"]["calibration"]["artefact"] = str(artefact)
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")

    result = run(cfg_path)

    model_findings = [
        finding
        for finding in result.findings
        if finding.score_type is ScoreType.MODEL_SCORE and finding.category == "financial"
    ]
    assert model_findings  # doc_born_001 produces one
    assert all(
        finding.calibration_status is CalibrationStatus.PROVISIONAL
        for finding in model_findings
    )
    assert result.reconcile.reconciled
