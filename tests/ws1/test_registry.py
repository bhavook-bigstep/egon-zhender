"""JobRegistry: durable store + atomic queue + migration summary."""

from __future__ import annotations

from pathlib import Path

from libs.jobs import Job, JobRequest, JobResult, JobStatus, JobType
from libs.registry import JobRegistry
from libs.schemas import ReconcileReport


def _job(job_id: str, status: JobStatus = JobStatus.QUEUED) -> Job:
    return Job(
        job_id=job_id,
        request=JobRequest(job_type=JobType.BATCH, config_version="v"),
        status=status,
        created_at=f"2026-01-01T00:00:0{job_id[-1]}",
    )


def test_create_get_list(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_job("a1"))
    assert reg.get("a1") is not None
    assert reg.get("a1").job_id == "a1"
    assert len(reg.list()) == 1


def test_claim_next_is_atomic_and_moves_to_running(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_job("a1"))
    reg.create(_job("a2"))
    first = reg.claim_next()
    second = reg.claim_next()
    assert first is not None and first.status is JobStatus.RUNNING
    assert second is not None and second.job_id != first.job_id
    assert reg.claim_next() is None  # both claimed


def test_request_cancel_sets_flag(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_job("a1"))
    assert reg.request_cancel("a1") is True
    assert reg.get("a1").cancel_requested is True


def test_migration_summary_aggregates_completed(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    job = _job("a1", JobStatus.COMPLETED)
    job.result = JobResult(
        job_id="a1",
        job_type=JobType.BATCH,
        status=JobStatus.COMPLETED,
        run_id="r",
        config_version="v",
        reconcile=ReconcileReport(
            input_count=5,
            flagged=3,
            not_flagged=1,
            unable_to_process=1,
            one_row_per_input=True,
            reconciled=True,
        ),
    )
    reg.create(job)
    summary = reg.migration_summary(authorised=5)
    assert summary.processed == 5
    assert (summary.flagged, summary.not_flagged, summary.unable_to_process) == (3, 1, 1)
    assert summary.pct_complete == 100.0
    assert summary.remaining == 0


def test_durability_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "r.db"
    reg = JobRegistry(path)
    reg.create(_job("a1"))
    reg.close()
    reopened = JobRegistry(path)
    assert reopened.get("a1") is not None


def _completed_job(job_id: str, status: JobStatus, flagged: int, unable: int) -> Job:
    job = _job(job_id, status)
    job.result = JobResult(
        job_id=job_id,
        job_type=JobType.BATCH,
        status=status,
        run_id="r",
        config_version="v",
        reconcile=ReconcileReport(
            input_count=flagged + unable,
            flagged=flagged,
            not_flagged=0,
            unable_to_process=unable,
            one_row_per_input=True,
            reconciled=True,
        ),
    )
    return job


def test_update_roundtrips_without_binding_error(tmp_path: Path) -> None:
    """Regression: update()'s column list must match its placeholders (created_at is
    NOT in the SET clause) — a mismatch previously raised sqlite3.ProgrammingError."""
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_job("a1"))
    job = _completed_job("a1", JobStatus.COMPLETED, flagged=2, unable=1)
    reg.update(job)  # must not raise
    reloaded = reg.get("a1")
    assert reloaded is not None
    assert reloaded.status is JobStatus.COMPLETED
    assert reloaded.result is not None and reloaded.result.reconcile.flagged == 2


def test_increment_progress_is_atomic_and_preserves_cancel(tmp_path: Path) -> None:
    """A progress bump must not clobber a concurrently-set cancel flag (finding A)."""
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_job("a1", JobStatus.RUNNING))
    reg.request_cancel("a1")
    reg.increment_progress("a1")
    reg.increment_progress("a1")
    reloaded = reg.get("a1")
    assert reloaded is not None
    assert reloaded.progress_done == 2
    assert reloaded.cancel_requested is True  # not lost


def test_migration_summary_includes_cancelled_and_failed(tmp_path: Path) -> None:
    """Cancelled/failed jobs carry finalised partial counts and must roll up (finding D)."""
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_completed_job("a1", JobStatus.COMPLETED, flagged=2, unable=0))
    reg.create(_completed_job("a2", JobStatus.CANCELLED, flagged=1, unable=1))
    reg.create(_completed_job("a3", JobStatus.FAILED, flagged=0, unable=1))
    summary = reg.migration_summary(authorised=10)
    # 2 + (1+1) + 1 = 5 processed across completed + cancelled + failed
    assert summary.processed == 5
    assert summary.flagged == 3
    assert summary.unable_to_process == 2


def test_upsert_replaces_without_pk_error(tmp_path: Path) -> None:
    """Interactive re-run uses a deterministic job_id; upsert must replace, not raise."""
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_job("a1", JobStatus.RUNNING))
    reg.upsert(_job("a1", JobStatus.COMPLETED))  # must not raise IntegrityError
    reloaded = reg.get("a1")
    assert reloaded is not None and reloaded.status is JobStatus.COMPLETED
    assert len(reg.list()) == 1  # still a single row


def test_upsert_inserts_when_absent(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    reg.upsert(_job("a1"))
    assert reg.get("a1") is not None


def test_request_cancel_unknown_job_returns_false(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    assert reg.request_cancel("nope") is False


def test_request_cancel_on_terminal_job_returns_false(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_completed_job("a1", JobStatus.COMPLETED, flagged=1, unable=0))
    assert reg.request_cancel("a1") is False
    reloaded = reg.get("a1")
    assert reloaded is not None and reloaded.cancel_requested is False


def test_migration_summary_counts_active_in_progress(tmp_path: Path) -> None:
    """An ACTIVE (RUNNING) job's progress_done rolls into in_progress and cuts remaining."""
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_completed_job("a1", JobStatus.COMPLETED, flagged=2, unable=0))
    running = _job("a2", JobStatus.RUNNING)
    running.progress_total = 5
    reg.create(running)
    reg.increment_progress("a2")
    reg.increment_progress("a2")
    summary = reg.migration_summary(authorised=10)
    assert summary.in_progress == 2
    assert summary.processed == 2  # only terminal counts are "processed"
    assert summary.remaining == 10 - 2 - 2


def test_migration_summary_clamps_completion_when_items_reprocessed(tmp_path: Path) -> None:
    """Re-running an item double-counts in `processed`; completion is clamped to 100%."""
    reg = JobRegistry(tmp_path / "r.db")
    reg.create(_completed_job("a1", JobStatus.COMPLETED, flagged=5, unable=0))
    reg.create(_completed_job("a2", JobStatus.COMPLETED, flagged=1, unable=0))  # re-run
    summary = reg.migration_summary(authorised=5)
    assert summary.processed == 6  # raw count stays truthful
    assert summary.pct_complete == 100.0  # never exceeds 100
    assert summary.remaining == 0
