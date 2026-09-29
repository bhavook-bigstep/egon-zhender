"""Privacy: no sensitive content in outputs or logs (Contract 2)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from libs.audit.redaction import redact, safe_stage_message
from pipelines.workstream1_sensitive.runner import RunResult
from tests.ws1.conftest import SENSITIVE_TOKENS


def test_outputs_carry_no_sensitive_content(run_ws1: Callable[..., RunResult]) -> None:
    result = run_ws1()
    summary_text = result.summary_path.read_text(encoding="utf-8")
    findings_text = result.findings_path.read_text(encoding="utf-8")
    ledger_text = result.ledger_path.read_text(encoding="utf-8")
    for token in SENSITIVE_TOKENS:
        assert token not in summary_text
        assert token not in findings_text
        assert token not in ledger_text


def test_logs_carry_no_sensitive_content(
    run_ws1: Callable[..., RunResult], caplog
) -> None:
    with caplog.at_level(logging.INFO):
        run_ws1()
    for token in SENSITIVE_TOKENS:
        assert token not in caplog.text


def test_redact_returns_length_only_placeholder() -> None:
    assert redact("secret") == "<redacted:6 chars>"


def test_safe_stage_message_is_ids_only() -> None:
    message = safe_stage_message("id1", "detect", "ok")
    assert "id1" in message
    assert "detect" in message
