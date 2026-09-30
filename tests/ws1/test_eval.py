"""Golden-truth loader + expected-vs-actual evaluation metrics (synthetic)."""

from __future__ import annotations

from pathlib import Path

from libs.eval.golden import GoldenTruth, load_golden_truth
from libs.eval.metrics import evaluate


def test_load_golden_truth(tmp_path: Path) -> None:
    (tmp_path / "manifest.jsonl").write_text(
        '{"source_id":"a1","expected_flag_status":"flagged",'
        '"expected_categories":["financial"],"scanned":true,"scan_severity":"heavy"}\n'
        '{"source_id":"a2","expected_flag_status":"not_flagged",'
        '"expected_categories":[],"scanned":false,"scan_severity":null}\n',
        encoding="utf-8",
    )
    (tmp_path / "labels.jsonl").write_text(
        '{"source_id":"a1","entity_type":"credit_debit_card","category":"financial",'
        '"in_taxonomy":true,"value":"4111"}\n'
        '{"source_id":"a1","entity_type":"email","category":"out_of_taxonomy",'
        '"in_taxonomy":false,"value":"x@y.z"}\n',
        encoding="utf-8",
    )
    truth = load_golden_truth(tmp_path)
    assert set(truth) == {"a1", "a2"}
    assert truth["a1"].expected_flag_status == "flagged"
    assert truth["a1"].scanned is True and truth["a1"].scan_severity == "heavy"
    assert len(truth["a1"].entities) == 2
    assert not hasattr(truth["a1"].entities[0], "value")  # content-free (no matched value)


_CATEGORIES = ["financial", "government_id", "health"]


def test_evaluate_metrics() -> None:
    truth = {
        "a1": GoldenTruth("a1", "flagged", ("financial",), True, "heavy", ()),
        "a2": GoldenTruth("a2", "not_flagged", (), False, None, ()),
        "a3": GoldenTruth("a3", "flagged", ("health",), False, None, ()),
    }
    results = [
        {"source_id": "a1", "flag_status": "flagged", "sensitivity_categories": ["financial"]},
        {"source_id": "a2", "flag_status": "flagged", "sensitivity_categories": ["financial"]},
        {"source_id": "a3", "flag_status": "not_flagged", "sensitivity_categories": []},
    ]
    rep = evaluate(results, truth, _CATEGORIES)
    assert rep["categories"] == _CATEGORIES  # from config, not a literal
    assert rep["counts"]["evaluated"] == 3
    counts = rep["counts"]
    assert (counts["flag_tp"], counts["flag_fp"], counts["flag_fn"]) == (1, 1, 1)
    assert rep["flagging"]["precision"] == 0.5 and rep["flagging"]["recall"] == 0.5
    financial = rep["by_category"]["financial"]
    assert financial["tp"] == 1 and financial["fp"] == 1
    # government_id is in the taxonomy but never expected/actual here — all-zero denominators
    assert rep["by_category"]["government_id"] == {
        "precision": 0.0, "recall": 0.0, "f1": 0.0, "tp": 0, "fp": 0, "fn": 0,
    }
    assert rep["by_scanned"]["scanned"]["recall"] == 1.0  # a1 scanned, expected+found
    assert rep["by_scanned"]["born_digital"]["recall"] == 0.0  # a3 expected but not found
    row_a1 = next(r for r in rep["rows"] if r["source_id"] == "a1")
    assert row_a1["flag_match"] and row_a1["categories_match"]
    # a2: predicted financial where none expected — a real category mismatch
    row_a2 = next(r for r in rep["rows"] if r["source_id"] == "a2")
    assert row_a2["categories_match"] is False
    assert row_a2["actual_categories"] == ["financial"]


def test_evaluate_excludes_unable_to_process() -> None:
    """A processing failure is surfaced, never scored as a correct not-flagged negative."""
    truth = {
        "a1": GoldenTruth("a1", "not_flagged", (), False, None, ()),
        "a2": GoldenTruth("a2", "flagged", ("financial",), False, None, ()),
    }
    results = [
        {"source_id": "a1", "flag_status": "unable_to_process", "sensitivity_categories": []},
        {"source_id": "a2", "flag_status": "flagged", "sensitivity_categories": ["financial"]},
    ]
    rep = evaluate(results, truth, _CATEGORIES)
    counts = rep["counts"]
    assert counts["unable_to_process"] == 1
    assert counts["evaluated"] == 1  # only a2 is a real determination
    # a1 must NOT be folded into the confusion matrix as a true negative
    assert (counts["flag_tp"], counts["flag_fp"], counts["flag_fn"], counts["flag_tn"]) == (
        1, 0, 0, 0,
    )
    row_a1 = next(r for r in rep["rows"] if r["source_id"] == "a1")
    assert row_a1["actual_flag_status"] == "unable_to_process"
    assert row_a1["flag_match"] is None and row_a1["categories_match"] is None


def test_evaluate_skips_unprocessed_records() -> None:
    truth = {"a1": GoldenTruth("a1", "flagged", ("financial",), False, None, ())}
    rep = evaluate([], truth, _CATEGORIES)  # nothing processed
    assert rep["counts"]["evaluated"] == 0
    assert rep["rows"] == []
