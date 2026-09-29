"""Worker fail-loud: a failing job is recorded FAILED and the worker keeps draining."""

from __future__ import annotations

import time
from pathlib import Path

from libs.jobs import Job, JobRequest, JobStatus, JobType
from libs.registry import JobRegistry
from pipelines.workstream1_sensitive.worker import Worker


class _RaisingService:
    """Stand-in JobService whose execute always raises (drives the fail-loud path)."""

    def execute(self, job: Job) -> Job:
        raise RuntimeError("boom")


class _FlakyClaimRegistry(JobRegistry):
    """Registry whose first claim_next raises, to prove the worker survives it."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self.claim_calls = 0

    def claim_next(self) -> Job | None:
        self.claim_calls += 1
        if self.claim_calls == 1:
            raise RuntimeError("transient claim error")
        return super().claim_next()


def _queued(job_id: str) -> Job:
    return Job(
        job_id=job_id,
        request=JobRequest(job_type=JobType.BATCH, config_version="v"),
        status=JobStatus.QUEUED,
        created_at="2026-01-01T00:00:00",
    )


def _wait_status(
    reg: JobRegistry, job_id: str, status: JobStatus, timeout: float = 5.0
) -> Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = reg.get(job_id)
        if job is not None and job.status is status:
            return job
        time.sleep(0.02)
    raise AssertionError(f"{job_id} did not reach {status}")


def test_worker_marks_failing_job_failed_and_survives(tmp_path: Path) -> None:
    reg = JobRegistry(tmp_path / "r.db")
    worker = Worker(_RaisingService(), reg, poll_seconds=0.02)  # type: ignore[arg-type]
    worker.start()
    try:
        reg.create(_queued("a1"))
        failed = _wait_status(reg, "a1", JobStatus.FAILED)
        assert failed.exception == "worker execution error"
        # Still alive: a second queued job is also drained (→ FAILED), not left stuck.
        reg.create(_queued("a2"))
        _wait_status(reg, "a2", JobStatus.FAILED)
        assert worker.is_alive()
    finally:
        worker.stop()
        worker.join(timeout=2)


def test_worker_survives_claim_next_error(tmp_path: Path) -> None:
    reg = _FlakyClaimRegistry(tmp_path / "r.db")
    worker = Worker(_RaisingService(), reg, poll_seconds=0.02)  # type: ignore[arg-type]
    worker.start()
    try:
        reg.create(_queued("a1"))
        # The first claim_next raised; the worker must recover and still process a1.
        _wait_status(reg, "a1", JobStatus.FAILED)
        assert reg.claim_calls >= 2
        assert worker.is_alive()
    finally:
        worker.stop()
        worker.join(timeout=2)
