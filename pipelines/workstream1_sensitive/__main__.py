"""CLI entry point for WS-1 (headless). Runs through JobService so every run is recorded
in the registry — the same store the API/admin page reads.

Batch (whole manifest):
    python -m pipelines.workstream1_sensitive --config config/ws1.yaml
Single job (one authorised source_id):
    python -m pipelines.workstream1_sensitive --config config/ws1.yaml --source-id note_001

Prints only non-sensitive counts and the reconciliation report — never content.
"""

from __future__ import annotations

import argparse
import logging
import os

from libs.config import load_ws1_config
from libs.jobs import Job, JobRequest, JobType
from libs.registry import JobRegistry
from pipelines.workstream1_sensitive.job_service import JobService


def _print_job(job: Job) -> int:
    print(f"job_id={job.job_id} status={job.status.value} run_id={job.run_id}")
    if job.exception:
        print(f"exception: {job.exception}")
        return 1
    result = job.result
    if result is None:
        return 1
    report = result.reconcile
    print(
        "reconcile: "
        f"input={report.input_count} flagged={report.flagged} "
        f"not_flagged={report.not_flagged} "
        f"unable_to_process={report.unable_to_process} reconciled={report.reconciled}"
    )
    for summary in result.items:  # inline only for single jobs
        print(
            f"{summary.source_id} | {summary.flag_status.value} | "
            f"cats={summary.sensitivity_categories} | reason={summary.reason_summary}"
        )
    print(f"outputs: {result.summary_path} | {result.findings_path} | {result.ledger_path}")
    return 0 if report.reconciled else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the WS-1 sensitive-data pipeline.")
    parser.add_argument("--config", default="config/ws1.yaml")
    parser.add_argument("--source-id", default=None, help="Run a single job for one id.")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--registry",
        default=os.environ.get("WS1_REGISTRY_DB", "poc/registry.db"),
        help="Path to the run registry (SQLite).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_ws1_config(args.config)
    registry = JobRegistry(args.registry)
    service = JobService(args.config, registry)

    if args.source_id:
        request = JobRequest(
            job_type=JobType.SINGLE,
            config_version=cfg.config_version,
            source_ids=[args.source_id],
        )
    else:
        request = JobRequest(
            job_type=JobType.BATCH,
            config_version=cfg.config_version,
            source_ids=None,
            max_concurrency=args.max_concurrency,
            resume=args.resume,
        )
    job = service.run_now(request)
    registry.close()
    return _print_job(job)


if __name__ == "__main__":
    raise SystemExit(main())
