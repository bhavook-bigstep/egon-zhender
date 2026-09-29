"""Job schema for WS-1 — one model, two request/execution strategies.

Both single and bulk jobs select from the **frozen, authorised manifest** (by
source_id) and produce the same `JobResult` shape, so callers never branch on mode.
Single = one id (low latency, inline rows); batch = many (throughput, rows on disk).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from libs.schemas import Finding, ReconcileReport, Ws1Summary


class JobType(StrEnum):
    SINGLE = "single"
    BATCH = "batch"


class JobStatus(StrEnum):
    # PENDING/RETRYING are reserved for the production queue backend (a pre-enqueue
    # state and automatic retry); the PoC in-process worker uses QUEUED→RUNNING→terminal
    # and never sets them. Kept so the schema and admin roll-up are forward-compatible.
    PENDING = "pending"
    QUEUED = "queued"  # enqueued, awaiting a worker
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"  # reconciled; every selected item produced a row
    FAILED = "failed"  # run-level failure (bad config/manifest) — not item errors
    CANCELLED = "cancelled"


class JobRequest(BaseModel):
    """What to process and how. Selection is always by authorised source_id."""

    job_type: JobType
    config_version: str  # must match the loaded config (reproducibility guard)
    source_ids: list[str] | None = None  # None ⇒ the whole frozen manifest
    # batch-only execution hints (ignored for SINGLE):
    max_concurrency: int = 1
    batch_size: int = 500
    resume: bool = False


class JobResult(BaseModel):
    """Uniform result for both modes."""

    job_id: str
    job_type: JobType
    status: JobStatus
    run_id: str
    config_version: str
    reconcile: ReconcileReport
    item_statuses: dict[str, str] = Field(default_factory=dict)  # source_id -> status
    summary_path: str | None = None  # result-set locations
    findings_path: str | None = None
    ledger_path: str | None = None
    started_at: str = ""
    finished_at: str = ""
    exception: str | None = None  # run-level only
    # Inline rows — populated for SINGLE (convenience); empty for BATCH (see paths).
    items: list[Ws1Summary] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class Job(BaseModel):
    """A durable, pollable job record (registry row)."""

    job_id: str
    request: JobRequest
    status: JobStatus
    run_id: str = ""
    progress_done: int = 0
    progress_total: int = 0
    result: JobResult | None = None
    exception: str | None = None
    cancel_requested: bool = False
    created_at: str = ""
    updated_at: str = ""


class MigrationSummary(BaseModel):
    """Migration-wide reconciliation for the admin panel (response §3.5)."""

    authorised: int = 0  # total items in the manifest
    processed: int = 0  # flagged + not_flagged + unable_to_process
    flagged: int = 0
    not_flagged: int = 0
    unable_to_process: int = 0
    in_progress: int = 0  # items currently being processed
    remaining: int = 0  # authorised - processed - in_progress
    pct_complete: float = 0.0
    jobs_total: int = 0
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
