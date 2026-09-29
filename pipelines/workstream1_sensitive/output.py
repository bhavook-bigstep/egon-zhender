"""Stage 7 — Output assembly.

Writes the result set to a separate location (never the source), sorted for
reproducibility (Contract 4). Rows are content-free by construction (evidence by
location only).
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.audit.ledger import RunLedger
from libs.schemas import Finding, ReconcileReport, Ws1Config, Ws1Summary

_SUPPORTED_FORMATS = frozenset({"jsonl"})


def write_outputs(
    summaries: list[Ws1Summary],
    findings: list[Finding],
    cfg: Ws1Config,
) -> tuple[Path, Path]:
    """Write the item-summary and findings JSONL files; return their paths."""
    if cfg.output.format not in _SUPPORTED_FORMATS:
        raise ValueError(f"unsupported output format: {cfg.output.format}")
    result_dir = Path(cfg.output.result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    summary_path = result_dir / "ws1_item_summary.jsonl"
    findings_path = result_dir / "ws1_findings.jsonl"

    ordered_summaries = sorted(summaries, key=lambda row: row.source_id)
    ordered_findings = sorted(
        findings, key=lambda row: (row.source_id, row.finding_id)
    )

    with summary_path.open("w", encoding="utf-8") as handle:
        for summary_row in ordered_summaries:
            handle.write(summary_row.model_dump_json() + "\n")

    with findings_path.open("w", encoding="utf-8") as handle:
        for finding_row in ordered_findings:
            handle.write(finding_row.model_dump_json() + "\n")

    return summary_path, findings_path


def write_ledger(
    ledger: RunLedger,
    reconcile: ReconcileReport,
    cfg: Ws1Config,
) -> Path:
    """Persist the run ledger + reconciliation as an on-disk audit artifact (Contract 4).

    Content-free by construction: stage events carry only source IDs, stage names,
    outcomes, typed exception codes, and non-sensitive numeric metrics.
    """
    result_dir = Path(cfg.output.result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = result_dir / "ws1_run_ledger.json"
    record = {
        "run_id": ledger.run_id,
        "config_version": ledger.config_version,
        "engines": {
            "extract": cfg.extract.engine,
            "detect": cfg.detect.engine,
            "detector_version": cfg.detect.detector_version,
            "ocr": cfg.ocr.provider,
            "inference_provider": cfg.inference.provider,
            "model_version": cfg.inference.model_version,
        },
        "reconcile": reconcile.model_dump(),
        "stage_events": [
            {
                "source_id": event.source_id,
                "stage": event.stage,
                "outcome": event.outcome,
                "exception_code": (
                    event.exception_code.value if event.exception_code else None
                ),
                "detail": event.detail,
            }
            for event in ledger.events
        ],
        "final_status": ledger.final_statuses(),
    }
    with ledger_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return ledger_path
