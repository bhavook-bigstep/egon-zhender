"""End-to-end: skeleton output matches the synthetic truth set."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from pipelines.workstream1_sensitive.runner import RunResult


def test_output_matches_truth(run_ws1: Callable[..., RunResult]) -> None:
    result = run_ws1()
    truth = json.loads(
        Path("tests/fixtures/ws1_truth.json").read_text(encoding="utf-8")
    )
    by_id = {summary.source_id: summary for summary in result.summaries}

    assert set(by_id) == set(truth)
    for source_id, expected in truth.items():
        summary = by_id[source_id]
        assert summary.flag_status.value == expected["flag_status"]
        if "categories" in expected:
            assert summary.sensitivity_categories == expected["categories"]
        expected_type = expected.get("strongest_score_type")
        if expected_type is not None:
            assert summary.strongest_score_type is not None
            assert summary.strongest_score_type.value == expected_type
        if "exception_code" in expected:
            assert summary.exception_code is not None
            assert summary.exception_code.value == expected["exception_code"]
