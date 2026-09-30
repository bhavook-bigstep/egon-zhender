"""Tests for build_labels: content-free (score, binary label) calibration splits."""

from __future__ import annotations

from libs.eval.calibration_labels import build_labels
from libs.eval.golden import GoldenTruth


def _finding(source_id: str, category: str, score: float | None) -> dict:
    score_type = "MODEL_SCORE" if score is not None else "DETERMINISTIC"
    return {
        "source_id": source_id,
        "category": category,
        "score": score,
        "score_type": score_type,
    }


def _truth() -> dict[str, GoldenTruth]:
    return {
        "a1": GoldenTruth("a1", "flagged", ("financial",), False, None, ()),
        "a2": GoldenTruth("a2", "flagged", ("financial",), False, None, ()),
    }


def test_determinism_same_inputs_same_split() -> None:
    findings = [_finding(f"a{i % 2 + 1}", "financial", 0.1 * i) for i in range(20)]
    truth = {
        "a1": GoldenTruth("a1", "flagged", ("financial",), False, None, ()),
        "a2": GoldenTruth("a2", "not_flagged", (), False, None, ()),
    }
    first = build_labels(findings, truth, seed=1729)
    second = build_labels(findings, truth, seed=1729)
    assert first == second
    # A different seed generally yields a different shuffle (hence a different split).
    other = build_labels(findings, truth, seed=1)
    assert other != first


def test_label_derivation_in_and_out_of_expected() -> None:
    findings = [
        _finding("a1", "financial", 0.9),  # expected for a1 -> label 1
        _finding("a1", "health", 0.8),  # not expected for a1 -> label 0
    ]
    labels = build_labels(findings, _truth(), holdout_frac=0.0)
    assert labels["financial"]["dev"] == [(0.9, 1)]
    assert labels["health"]["dev"] == [(0.8, 0)]


def test_skips_none_score_findings() -> None:
    findings = [
        _finding("a1", "financial", None),  # deterministic, no score -> skipped
        _finding("a2", "financial", 0.5),
    ]
    labels = build_labels(findings, _truth(), holdout_frac=0.0)
    assert labels == {"financial": {"dev": [(0.5, 1)], "holdout": []}}


def test_skips_unknown_source_id() -> None:
    findings = [
        _finding("ghost", "financial", 0.7),  # not in truth -> skipped
        _finding("a1", "financial", 0.6),
    ]
    labels = build_labels(findings, _truth(), holdout_frac=0.0)
    assert labels == {"financial": {"dev": [(0.6, 1)], "holdout": []}}


def test_holdout_split_sizes_and_no_empty_categories() -> None:
    findings = [_finding("a1", "financial", 0.05 * i) for i in range(10)]
    labels = build_labels(findings, _truth(), holdout_frac=0.4)
    dev = labels["financial"]["dev"]
    holdout = labels["financial"]["holdout"]
    assert len(holdout) == 4 and len(dev) == 6
    assert len(dev) + len(holdout) == 10
    # No category with zero pairs is emitted.
    assert build_labels([], _truth()) == {}


def test_build_labels_feeds_fit_calibrator_provisional() -> None:
    """A small labelled set → fit_calibrator yields PROVISIONAL (< min_positives)."""
    from libs.calibration import fit_calibrator

    truth = {
        f"s{i}": GoldenTruth(f"s{i}", "flagged", ("financial",), False, None, ())
        for i in range(6)
    }
    findings = [
        {"source_id": f"s{i}", "category": "financial",
         "score": 70.0 + i, "score_type": "classifier_score"}
        for i in range(6)
    ]
    labels = build_labels(findings, truth, seed=1)
    cal = fit_calibrator(labels, version="t", method="identity",
                         min_positives=100, max_holdout_error=5.0)
    dumped = cal.to_dict()["categories"]["financial"]
    assert dumped["status"] == "provisional"  # 6 positives << 100 → not CALIBRATED
