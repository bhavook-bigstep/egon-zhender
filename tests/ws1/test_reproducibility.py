"""Reproducibility: same manifest + config + seed → identical output (Contract 4)."""

from __future__ import annotations

from collections.abc import Callable

from pipelines.workstream1_sensitive.runner import RunResult


def test_same_inputs_produce_identical_output(
    run_ws1: Callable[..., RunResult],
) -> None:
    first = run_ws1("a")
    second = run_ws1("b")
    assert first.run_id == second.run_id
    assert first.summary_path.read_bytes() == second.summary_path.read_bytes()
    assert first.findings_path.read_bytes() == second.findings_path.read_bytes()
    assert first.ledger_path.read_bytes() == second.ledger_path.read_bytes()
