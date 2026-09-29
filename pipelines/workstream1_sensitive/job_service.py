"""JobService — the single entry for CLI (headless) and API.

Wraps the executors (`run_single`/`run_batch`/`process_item`), records every job to the
durable registry, drives progress + cooperative cancel, and streams stage events for the
interactive single-job view. Nothing is UI-only; headless runs are observable.
"""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from libs.audit.ledger import StageEvent
from libs.config import load_ws1_config
from libs.jobs import Job, JobRequest, JobResult, JobStatus, JobType
from libs.registry import JobRegistry
from libs.schemas import FlagStatus, Ws1Config
from pipelines.workstream1_sensitive.job_runner import run_batch, run_single
from pipelines.workstream1_sensitive.runner import (
    build_reader,
    compute_run_id,
)

_UNABLE = FlagStatus.UNABLE_TO_PROCESS.value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _event_dict(event: StageEvent) -> dict[str, Any]:
    return {
        "source_id": event.source_id,
        "stage": event.stage,
        "outcome": event.outcome,
        "exception_code": event.exception_code.value if event.exception_code else None,
        "detail": dict(event.detail),  # content-free metrics for the step-by-step view
        "records": [dict(r) for r in event.records],  # per-step reasoning trace
    }


class JobService:
    def __init__(self, config_path: str | Path, registry: JobRegistry) -> None:
        self._config_path = str(config_path)
        self._registry = registry

    # --- selection / validation ---

    def _resolve(
        self, cfg: Ws1Config, request: JobRequest
    ) -> tuple[list[str] | None, str | None]:
        if request.config_version != cfg.config_version:
            return None, (
                f"config_version mismatch: request={request.config_version} "
                f"config={cfg.config_version}"
            )
        ids = [entry.source_id for entry in build_reader(cfg).list_manifest()]
        if request.source_ids is None:
            return ids, None
        missing = [sid for sid in request.source_ids if sid not in set(ids)]
        if missing:
            return None, f"source_ids not in manifest: {missing}"
        return list(request.source_ids), None

    # --- enqueue (API) ---

    def submit(self, request: JobRequest) -> Job:
        """Validate + enqueue a job for the worker; returns immediately (QUEUED)."""
        cfg = load_ws1_config(self._config_path)
        job = Job(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            request=request,
            status=JobStatus.QUEUED,
            created_at=_now(),
        )
        selected, err = self._resolve(cfg, request)
        if err:
            job.status = JobStatus.FAILED
            job.exception = err
            return self._registry.create(job)
        job.progress_total = len(selected or [])
        return self._registry.create(job)

    # --- worker execution ---

    @staticmethod
    def _apply_result(job: Job, result: JobResult) -> None:
        """Fold a terminal JobResult onto the job record (status/run_id/counts/exception).

        Shared by `execute` and `run_now` so neither path can drop `result.exception`
        on a failed run.
        """
        job.status = result.status
        job.run_id = result.run_id
        job.result = result
        job.progress_done = result.reconcile.input_count
        job.exception = result.exception

    def execute(self, job: Job) -> Job:
        """Run a claimed batch job to completion, updating the registry as it goes."""

        def on_progress(_source_id: str, _status: str) -> None:
            # Atomic bump: never lose a concurrent cancel flag to a read-modify-write
            # of the whole record.
            self._registry.increment_progress(job.job_id)

        def should_cancel() -> bool:
            current = self._registry.get(job.job_id)
            return bool(current and current.cancel_requested)

        result = run_batch(
            self._config_path, job.request, on_progress=on_progress, should_cancel=should_cancel
        )
        current = self._registry.get(job.job_id) or job
        self._apply_result(current, result)
        return self._registry.update(current)

    # --- synchronous (CLI headless) ---

    def run_now(self, request: JobRequest) -> Job:
        """Run synchronously and record it (used by the CLI so headless runs register)."""
        cfg = load_ws1_config(self._config_path)
        job = Job(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            request=request,
            status=JobStatus.RUNNING,
            created_at=_now(),
        )
        selected, err = self._resolve(cfg, request)
        if err:
            job.status = JobStatus.FAILED
            job.exception = err
            return self._registry.create(job)
        job.progress_total = len(selected or [])
        self._registry.create(job)

        if request.job_type == JobType.BATCH:
            result = run_batch(self._config_path, request)
        else:
            result = run_single(self._config_path, request)
        self._apply_result(job, result)
        return self._registry.update(job)

    # --- controls ---

    def cancel(self, job_id: str) -> bool:
        return self._registry.request_cancel(job_id)

    def retry_failed(self, job_id: str) -> Job | None:
        prior = self._registry.get(job_id)
        if prior is None or prior.result is None:
            return None
        failed = [
            sid for sid, status in prior.result.item_statuses.items() if status == _UNABLE
        ]
        if not failed:
            return None
        return self.submit(
            JobRequest(
                job_type=JobType.BATCH,
                config_version=prior.request.config_version,
                source_ids=failed,
            )
        )

    # --- interactive single-job stream (live view) ---

    def run_interactive(self, request: JobRequest) -> Iterator[dict[str, Any]]:
        """Run a single/small selection inline, yielding stage events live, then the result.

        Delegates the actual orchestration to `run_single` (the ONE single-job path):
        a worker thread runs it with an `on_event` hook that pushes each stage
        event onto a queue; this generator drains the queue and yields SSE frames, then the
        finished rows and the assembled result. No duplicate selection/output/assembly here.
        """
        cfg = load_ws1_config(self._config_path)
        selected_ids, err = self._resolve(cfg, request)
        if err or not selected_ids:
            yield {"event": "error", "message": err or "no source_ids selected"}
            return

        by_id = {entry.source_id: entry for entry in build_reader(cfg).list_manifest()}
        selected = [by_id[sid] for sid in selected_ids]
        run_id = compute_run_id(selected, cfg)
        # Unique registry id per run so EVERY interactive run is its own history entry
        # (a re-run of the same item no longer collapses onto a deterministic id). The
        # deterministic run_id is kept on the record for reproducibility/traceability.
        job_id = f"single-{uuid.uuid4().hex[:12]}"
        self._registry.create(
            Job(
                job_id=job_id,
                request=request,
                status=JobStatus.RUNNING,
                run_id=run_id,
                progress_total=len(selected),
                created_at=_now(),
            )
        )

        events: queue.Queue[Any] = queue.Queue()
        sentinel = object()
        box: dict[str, Any] = {}

        def worker() -> None:
            # Finalize the REGISTRY here (not after the yield loop) so the job always
            # reaches a terminal state even if the SSE client disconnects early and the
            # generator is abandoned. Always enqueue the sentinel so the stream never hangs.
            try:
                result = run_single(
                    self._config_path,
                    request,
                    on_event=lambda ev: events.put(("stage", ev)),
                )
                result.job_id = job_id  # align with the registry id (workbook link)
                box["result"] = result
                current = self._registry.get(job_id)
                if current is not None:
                    self._apply_result(current, result)
                    self._registry.update(current)
            except Exception as exc:  # fail loud: record FAILED + surface to the client
                box["error"] = str(exc)
                current = self._registry.get(job_id)
                if current is not None:
                    current.status = JobStatus.FAILED
                    current.exception = str(exc)
                    self._registry.update(current)
            finally:
                events.put(sentinel)

        thread = threading.Thread(target=worker)
        thread.start()
        while True:
            message = events.get()
            if message is sentinel:
                break
            kind, payload = message
            if kind == "stage":
                yield {"event": "stage", **_event_dict(payload)}
        thread.join()

        if "error" in box:
            yield {"event": "error", "message": box["error"]}
            return

        result: JobResult = box["result"]
        for row in result.items:
            yield {"event": "item", "row": row.model_dump(mode="json")}
        yield {"event": "done", "result": result.model_dump(mode="json")}
