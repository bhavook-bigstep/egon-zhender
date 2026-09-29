"""Job runner — single-job path (batch path added next).

Single jobs select one (or a few) authorised source_ids from the frozen manifest,
process them through the shared per-item core, write a job-namespaced result set, and
return a `JobResult` with the rows inline. Reproducible (`run_id` over the selected
slice) and reconciled, exactly like a full run.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import UTC, datetime
from pathlib import Path

from libs.audit.ledger import RunLedger, StageEvent
from libs.config import load_ws1_config
from libs.jobs import JobRequest, JobResult, JobStatus, JobType
from libs.schemas import Finding, FlagStatus, ManifestEntry, ReconcileReport, Ws1Summary
from pipelines.workstream1_sensitive.output import write_ledger, write_outputs
from pipelines.workstream1_sensitive.runner import (
    Ws1Context,
    build_context,
    compute_run_id,
    process_item,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _empty_reconcile() -> ReconcileReport:
    return ReconcileReport(
        input_count=0,
        flagged=0,
        not_flagged=0,
        unable_to_process=0,
        one_row_per_input=False,
        reconciled=False,
    )


def _failed(job_type: JobType, config_version: str, message: str, started: str) -> JobResult:
    return JobResult(
        job_id=f"{job_type.value}-invalid",
        job_type=job_type,
        status=JobStatus.FAILED,
        run_id="",
        config_version=config_version,
        reconcile=_empty_reconcile(),
        started_at=started,
        finished_at=_now(),
        exception=message,
    )


def run_single(
    config_path: str | Path,
    request: JobRequest,
    on_event: Callable[[StageEvent], None] | None = None,
) -> JobResult:
    """Run a single (or small, explicit) selection synchronously.

    `on_event` (optional) streams each stage event live — used by the interactive view,
    so `run_single` is the ONE place single-job orchestration lives (no duplicate path).
    """
    started = _now()
    cfg = load_ws1_config(config_path)

    if request.config_version != cfg.config_version:
        return _failed(
            request.job_type,
            request.config_version,
            f"config_version mismatch: request={request.config_version} "
            f"config={cfg.config_version}",
            started,
        )
    if not request.source_ids:
        return _failed(
            request.job_type,
            request.config_version,
            "single job requires at least one source_id",
            started,
        )

    ctx = build_context(cfg)
    by_id = {entry.source_id: entry for entry in ctx.reader.list_manifest()}
    missing = [sid for sid in request.source_ids if sid not in by_id]
    if missing:
        return _failed(
            request.job_type,
            request.config_version,
            f"source_ids not in manifest: {missing}",
            started,
        )
    selected = [by_id[sid] for sid in request.source_ids]

    run_id = compute_run_id(selected, cfg)
    job_id = f"{request.job_type.value}-{run_id}"
    snapshot_id = f"sample:{Path(cfg.source.manifest).stem}"
    ledger = RunLedger(run_id, cfg.config_version, on_event=on_event)

    # Namespace the result set per job so single runs never clobber a batch run.
    job_dir = Path(cfg.output.result_dir) / job_id
    job_cfg = cfg.model_copy(
        update={"output": cfg.output.model_copy(update={"result_dir": str(job_dir)})}
    )

    summaries = []
    findings = []
    for entry in selected:
        summary, item_findings = process_item(ctx, entry, run_id, snapshot_id, ledger)
        summaries.append(summary)
        findings.extend(item_findings)

    reconcile = ledger.reconcile(len(selected))
    summary_path, findings_path = write_outputs(summaries, findings, job_cfg)
    ledger_path = write_ledger(ledger, reconcile, job_cfg)

    return JobResult(
        job_id=job_id,
        job_type=request.job_type,
        status=JobStatus.COMPLETED,
        run_id=run_id,
        config_version=cfg.config_version,
        reconcile=reconcile,
        item_statuses=ledger.final_statuses(),
        summary_path=str(summary_path),
        findings_path=str(findings_path),
        ledger_path=str(ledger_path),
        started_at=started,
        finished_at=_now(),
        items=summaries,
        findings=findings,
    )


# --- Batch job path (bounded concurrency + checkpoint/resume) ---

_LocalResult = tuple[Ws1Summary, list[Finding], RunLedger]


def _process_one_local(
    ctx: Ws1Context, entry: ManifestEntry, run_id: str, snapshot_id: str
) -> _LocalResult:
    """Process one item with its OWN ledger (thread-safe; merged later)."""
    local = RunLedger(run_id, ctx.cfg.config_version)
    summary, findings = process_item(ctx, entry, run_id, snapshot_id, local)
    return summary, findings, local


def _load_prior(result_dir: Path) -> tuple[list[Ws1Summary], list[Finding], dict[str, str]]:
    """Read a prior run's rows + final statuses for resume (empty if none)."""
    summaries: list[Ws1Summary] = []
    findings: list[Finding] = []
    done: dict[str, str] = {}
    summ = result_dir / "ws1_item_summary.jsonl"
    find = result_dir / "ws1_findings.jsonl"
    ledger = result_dir / "ws1_run_ledger.json"
    if summ.exists():
        summaries = [
            Ws1Summary.model_validate_json(line)
            for line in summ.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if find.exists():
        findings = [
            Finding.model_validate_json(line)
            for line in find.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if ledger.exists():
        done = json.loads(ledger.read_text(encoding="utf-8")).get("final_status", {})
    return summaries, findings, done


def _assemble(
    resumed_summaries: list[Ws1Summary],
    resumed_findings: list[Finding],
    resumed_finals: dict[str, FlagStatus],
    local_by_id: dict[str, _LocalResult],
    run_id: str,
    config_version: str,
) -> tuple[list[Ws1Summary], list[Finding], RunLedger]:
    """Deterministically merge resumed + freshly-processed items (sorted by id)."""
    ledger = RunLedger(run_id, config_version)
    for source_id, status in resumed_finals.items():
        ledger.record_final(source_id, status)
    summaries = list(resumed_summaries)
    findings = list(resumed_findings)
    for source_id in sorted(local_by_id):
        summary, item_findings, local = local_by_id[source_id]
        summaries.append(summary)
        findings.extend(item_findings)
        ledger.absorb(local)
    return summaries, findings, ledger


def run_batch(
    config_path: str | Path,
    request: JobRequest,
    on_progress: Callable[[str, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> JobResult:
    """Run a batch selection with bounded concurrency, checkpointing, and resume.

    `on_progress(source_id, flag_status)` fires as each item finishes; `should_cancel()`
    is checked between items — when true, no new items are launched (cooperative cancel),
    and the run reconciles over what was processed.
    """
    started = _now()
    cfg = load_ws1_config(config_path)
    if request.config_version != cfg.config_version:
        return _failed(
            request.job_type,
            request.config_version,
            f"config_version mismatch: request={request.config_version} "
            f"config={cfg.config_version}",
            started,
        )

    ctx = build_context(cfg)
    all_entries = ctx.reader.list_manifest()
    by_id = {entry.source_id: entry for entry in all_entries}
    if request.source_ids is None:
        selected = all_entries
    else:
        missing = [sid for sid in request.source_ids if sid not in by_id]
        if missing:
            return _failed(
                request.job_type,
                request.config_version,
                f"source_ids not in manifest: {missing}",
                started,
            )
        selected = [by_id[sid] for sid in request.source_ids]

    run_id = compute_run_id(selected, cfg)
    job_id = f"batch-{run_id}"
    snapshot_id = f"sample:{Path(cfg.source.manifest).stem}"

    # Namespace the result set per run so distinct batches never clobber each other and
    # resume reads only THIS run's prior partial. Because run_id is derived from the
    # selection + config + seed, a resumable prior under batch-<run_id>/ is by construction
    # the same selection + config — resume is self-gating.
    result_dir = Path(cfg.output.result_dir) / job_id
    job_cfg = cfg.model_copy(
        update={"output": cfg.output.model_copy(update={"result_dir": str(result_dir)})}
    )

    resumed_summaries: list[Ws1Summary] = []
    resumed_findings: list[Finding] = []
    resumed_finals: dict[str, FlagStatus] = {}
    if request.resume:
        prior_summaries, prior_findings, prior_done = _load_prior(result_dir)
        selected_ids = {e.source_id for e in selected}
        # Only carry forward prior items still in this selection.
        done_ids = set(prior_done) & selected_ids
        resumed_summaries = [s for s in prior_summaries if s.source_id in done_ids]
        resumed_findings = [f for f in prior_findings if f.source_id in done_ids]
        resumed_finals = {
            sid: FlagStatus(st) for sid, st in prior_done.items() if sid in done_ids
        }
    else:
        done_ids = set()

    to_process = [e for e in selected if e.source_id not in done_ids]

    local_by_id: dict[str, _LocalResult] = {}
    completed = 0
    cancelled = False
    workers = max(1, request.max_concurrency)
    entries_iter = iter(to_process)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = set()
        for _ in range(workers):  # prime the window
            entry = next(entries_iter, None)
            if entry is None:
                break
            pending.add(executor.submit(_process_one_local, ctx, entry, run_id, snapshot_id))
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                summary, item_findings, local = future.result()
                local_by_id[summary.source_id] = (summary, item_findings, local)
                completed += 1
                if on_progress is not None:
                    on_progress(summary.source_id, summary.flag_status.value)
                if completed % request.batch_size == 0:  # checkpoint (resumable)
                    cp_s, cp_f, cp_l = _assemble(
                        resumed_summaries, resumed_findings, resumed_finals,
                        local_by_id, run_id, cfg.config_version,
                    )
                    write_outputs(cp_s, cp_f, job_cfg)
                    write_ledger(cp_l, cp_l.reconcile(len(cp_s)), job_cfg)
            if should_cancel is not None and should_cancel():
                cancelled = True
            if not cancelled:  # launch replacements for the ones that finished
                for _ in range(len(done)):
                    entry = next(entries_iter, None)
                    if entry is None:
                        break
                    pending.add(
                        executor.submit(_process_one_local, ctx, entry, run_id, snapshot_id)
                    )

    summaries, findings, ledger = _assemble(
        resumed_summaries, resumed_findings, resumed_finals,
        local_by_id, run_id, cfg.config_version,
    )
    reconcile = ledger.reconcile(len(summaries))  # over the PROCESSED set (cancel-safe)
    summary_path, findings_path = write_outputs(summaries, findings, job_cfg)
    ledger_path = write_ledger(ledger, reconcile, job_cfg)

    return JobResult(
        job_id=job_id,
        job_type=request.job_type,
        status=JobStatus.CANCELLED if cancelled else JobStatus.COMPLETED,
        run_id=run_id,
        config_version=cfg.config_version,
        reconcile=reconcile,
        item_statuses=ledger.final_statuses(),
        summary_path=str(summary_path),
        findings_path=str(findings_path),
        ledger_path=str(ledger_path),
        started_at=started,
        finished_at=_now(),
    )
