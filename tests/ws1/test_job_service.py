"""JobService: run_now, submit+execute, cancel, retry_failed, interactive stream."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from libs.jobs import JobRequest, JobStatus, JobType
from libs.registry import JobRegistry
from pipelines.workstream1_sensitive.job_service import JobService

CONFIG_VERSION = "ws1-0.1.0-poc"


def _service(tmp_path: Path) -> tuple[JobService, JobRegistry]:
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    registry = JobRegistry(tmp_path / "r.db")
    return JobService(str(cfg_path), registry), registry


def _req(job_type: JobType, **kw: object) -> JobRequest:
    kw.setdefault("config_version", CONFIG_VERSION)
    return JobRequest(job_type=job_type, **kw)  # type: ignore[arg-type]


def test_run_now_batch_registers_and_completes(tmp_path: Path) -> None:
    service, registry = _service(tmp_path)
    job = service.run_now(_req(JobType.BATCH, source_ids=None))
    assert job.status is JobStatus.COMPLETED
    assert job.result is not None and job.result.reconcile.input_count == 5
    assert registry.get(job.job_id).status is JobStatus.COMPLETED


def test_run_now_single(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    job = service.run_now(_req(JobType.SINGLE, source_ids=["note_001"]))
    assert job.status is JobStatus.COMPLETED
    assert job.result.items[0].flag_status.value == "flagged"


def test_submit_is_queued_then_execute(tmp_path: Path) -> None:
    service, registry = _service(tmp_path)
    job = service.submit(_req(JobType.BATCH, source_ids=None))
    assert job.status is JobStatus.QUEUED
    assert job.progress_total == 5
    claimed = registry.claim_next()
    assert claimed is not None
    done = service.execute(claimed)
    assert done.status is JobStatus.COMPLETED
    assert done.result.reconcile.reconciled


def test_submit_config_mismatch_fails(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    job = service.submit(_req(JobType.BATCH, config_version="wrong", source_ids=None))
    assert job.status is JobStatus.FAILED
    assert "config_version mismatch" in (job.exception or "")


def test_execute_honours_cancel(tmp_path: Path) -> None:
    service, registry = _service(tmp_path)
    job = service.submit(_req(JobType.BATCH, source_ids=None))
    registry.request_cancel(job.job_id)
    claimed = registry.claim_next()
    done = service.execute(claimed)
    assert done.status is JobStatus.CANCELLED


def test_retry_failed_targets_unable_items(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    job = service.run_now(_req(JobType.BATCH, source_ids=None))
    retry = service.retry_failed(job.job_id)
    assert retry is not None
    assert retry.request.source_ids == ["unreadable_001"]


def test_retry_failed_unknown_job_returns_none(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    assert service.retry_failed("does-not-exist") is None


def test_retry_failed_no_unable_items_returns_none(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    # A single job over a clean item has no unable_to_process rows to retry.
    job = service.run_now(_req(JobType.SINGLE, source_ids=["note_001"]))
    assert service.retry_failed(job.job_id) is None


def test_execute_failure_preserves_exception(tmp_path: Path) -> None:
    """A run-level failure must carry its exception onto the job record (finding C)."""
    service, registry = _service(tmp_path)
    service.submit(_req(JobType.BATCH, source_ids=None))
    claimed = registry.claim_next()
    assert claimed is not None
    # Force run_batch to return a FAILED result by corrupting the config version it sees.
    claimed.request.config_version = "wrong"
    done = service.execute(claimed)
    assert done.status is JobStatus.FAILED
    assert "config_version mismatch" in (done.exception or "")


def test_run_interactive_streams_events(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    events = list(service.run_interactive(_req(JobType.SINGLE, source_ids=["note_001"])))
    kinds = [e["event"] for e in events]
    assert "stage" in kinds
    assert "item" in kinds
    assert kinds[-1] == "done"
    # all stage events precede all item events (queue drained to sentinel first)
    last_stage = max(i for i, k in enumerate(kinds) if k == "stage")
    first_item = kinds.index("item")
    assert first_item > last_stage
    # stage events carry no content
    for e in events:
        assert "text" not in e


def test_run_interactive_emits_full_step_flow(tmp_path: Path) -> None:
    """Every pipeline step streams as a stage event with content-free detail metrics."""
    service, _ = _service(tmp_path)
    events = list(service.run_interactive(_req(JobType.SINGLE, source_ids=["note_001"])))
    stages = [e["stage"] for e in events if e["event"] == "stage"]
    for expected in ["ingest", "extract", "ocr_gate", "detect", "screen", "assess", "score"]:
        assert expected in stages, f"missing step: {expected}"
    detailed = [e for e in events if e["event"] == "stage" and e.get("detail")]
    assert detailed, "steps should carry content-free detail metrics"
    assert all(isinstance(e["detail"], dict) for e in detailed)
    # Each step carries a content-free reasoning trace (records), never matched strings.
    by_stage = {e["stage"]: e for e in events if e["event"] == "stage"}
    detect_records = by_stage["detect"]["records"]
    assert detect_records and {"entity", "category", "score_type", "location"} <= set(
        detect_records[0]
    )
    for rec in detect_records:  # location only, no matched value
        assert "location" in rec and "value" not in rec


def test_run_interactive_rerun_creates_distinct_history_entries(tmp_path: Path) -> None:
    """Each interactive run gets a unique registry id → a re-run is its own history entry."""
    service, registry = _service(tmp_path)
    first = list(service.run_interactive(_req(JobType.SINGLE, source_ids=["note_001"])))
    second = list(service.run_interactive(_req(JobType.SINGLE, source_ids=["note_001"])))
    assert first[-1]["event"] == "done"
    assert second[-1]["event"] == "done"
    jobs = registry.list()
    assert len(jobs) == 2  # two distinct runs recorded, not collapsed onto one id
    assert len({j.job_id for j in jobs}) == 2
    # the done event's job_id matches its registry record (workbook link resolves)
    assert first[-1]["result"]["job_id"] != second[-1]["result"]["job_id"]
    assert {first[-1]["result"]["job_id"], second[-1]["result"]["job_id"]} == {
        j.job_id for j in jobs
    }


def test_run_interactive_worker_error_yields_error_and_fails_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If run_single raises, the stream must not hang: emit error + mark the job FAILED."""
    service, registry = _service(tmp_path)

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(
        "pipelines.workstream1_sensitive.job_service.run_single", boom
    )
    events = list(service.run_interactive(_req(JobType.SINGLE, source_ids=["note_001"])))
    assert events[-1]["event"] == "error"
    assert "kaboom" in events[-1]["message"]
    jobs = registry.list()
    assert jobs and jobs[0].status is JobStatus.FAILED  # not stranded RUNNING
