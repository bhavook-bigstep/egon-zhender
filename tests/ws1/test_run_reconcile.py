"""Full-run reconciliation: one row per input, counts balance (Contract 4)."""

from __future__ import annotations

import json
from collections.abc import Callable

from pipelines.workstream1_sensitive.runner import RunResult


def test_reconcile_balances(run_ws1: Callable[..., RunResult]) -> None:
    result = run_ws1()
    report = result.reconcile
    assert report.reconciled
    assert report.one_row_per_input
    assert len(result.summaries) == 5
    assert (report.flagged, report.not_flagged, report.unable_to_process) == (3, 1, 1)
    assert report.input_count == 5


def test_run_ledger_is_persisted(run_ws1: Callable[..., RunResult]) -> None:
    result = run_ws1()
    assert result.ledger_path.exists()
    record = json.loads(result.ledger_path.read_text(encoding="utf-8"))
    assert record["run_id"] == result.run_id
    assert record["config_version"] == "ws1-0.1.0-poc"
    assert record["reconcile"]["reconciled"] is True
    # One final status per input item.
    assert len(record["final_status"]) == 5
    assert record["final_status"]["unreadable_001"] == "unable_to_process"
