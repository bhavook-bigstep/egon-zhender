"""Batch-job path: whole/selected manifest, concurrency determinism, resume."""

from __future__ import annotations

from pathlib import Path

import yaml

from libs.jobs import JobRequest, JobStatus, JobType
from pipelines.workstream1_sensitive.job_runner import run_batch

CONFIG_VERSION = "ws1-0.1.0-poc"


def _config_at(tmp_path: Path, subdir: str) -> str:
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / subdir)
    cfg_path = tmp_path / f"ws1-{subdir}.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    return str(cfg_path)


def _request(**kw: object) -> JobRequest:
    kw.setdefault("job_type", JobType.BATCH)
    kw.setdefault("config_version", CONFIG_VERSION)
    return JobRequest(**kw)  # type: ignore[arg-type]


def test_batch_whole_manifest(tmp_path: Path) -> None:
    result = run_batch(_config_at(tmp_path, "out"), _request(source_ids=None))
    assert result.status is JobStatus.COMPLETED
    assert result.job_type is JobType.BATCH
    report = result.reconcile
    assert report.reconciled
    assert (report.flagged, report.not_flagged, report.unable_to_process) == (3, 1, 1)
    assert len(result.item_statuses) == 5
    assert Path(result.summary_path).exists()


def test_batch_selected_subset(tmp_path: Path) -> None:
    result = run_batch(
        _config_at(tmp_path, "out"), _request(source_ids=["note_001", "note_002"])
    )
    assert result.reconcile.input_count == 2
    assert set(result.item_statuses) == {"note_001", "note_002"}


def test_batch_concurrency_is_deterministic(tmp_path: Path) -> None:
    seq = run_batch(_config_at(tmp_path, "seq"), _request(max_concurrency=1))
    par = run_batch(_config_at(tmp_path, "par"), _request(max_concurrency=4))
    assert seq.run_id == par.run_id
    assert seq.item_statuses == par.item_statuses
    # Output is sorted, so bytes are identical regardless of completion order.
    assert Path(seq.summary_path).read_bytes() == Path(par.summary_path).read_bytes()
    assert Path(seq.findings_path).read_bytes() == Path(par.findings_path).read_bytes()


def test_batch_cancel_launches_no_new_items(tmp_path: Path) -> None:
    """Cooperative cancel: once requested, no new item is launched and the run
    reconciles over only the processed slice (finding J)."""
    processed = {"n": 0}

    def bump(_sid: str, _status: str) -> None:
        processed["n"] += 1

    result = run_batch(
        _config_at(tmp_path, "out"),
        _request(source_ids=None, max_concurrency=1),
        on_progress=bump,
        should_cancel=lambda: processed["n"] >= 1,
    )
    assert result.status is JobStatus.CANCELLED
    assert len(result.item_statuses) == 1  # only the primed item; no replacements
    assert result.reconcile.input_count == 1  # reconciles over the processed set


def test_batch_resume_same_selection_processes_only_remaining(tmp_path: Path) -> None:
    """Resume is gated to the same run_id (selection + config), so a cancelled run's
    partial is picked up and only the remaining items run (findings E + F)."""
    config_path = _config_at(tmp_path, "out")
    processed = {"n": 0}

    def bump(_sid: str, _status: str) -> None:
        processed["n"] += 1

    first = run_batch(
        config_path,
        _request(source_ids=None, max_concurrency=1),
        on_progress=bump,
        should_cancel=lambda: processed["n"] >= 1,
    )
    assert first.status is JobStatus.CANCELLED
    assert len(first.item_statuses) == 1
    (done_id,) = first.item_statuses.keys()

    # Resume the SAME selection → same run_id → skips the done item, finishes the rest.
    resumed = run_batch(config_path, _request(source_ids=None, resume=True))
    assert resumed.status is JobStatus.COMPLETED
    assert resumed.reconcile.reconciled
    assert resumed.reconcile.input_count == 5
    assert len(resumed.item_statuses) == 5
    assert done_id in resumed.item_statuses


def test_batch_resume_different_selection_reprocesses_all(tmp_path: Path) -> None:
    """Resume is self-gating: a DIFFERENT selection → different run_id → nothing skipped."""
    config_path = _config_at(tmp_path, "out")
    processed = {"n": 0}

    def bump(_sid: str, _status: str) -> None:
        processed["n"] += 1

    cancelled = run_batch(
        config_path,
        _request(source_ids=["note_001", "note_002"], max_concurrency=1),
        on_progress=bump,
        should_cancel=lambda: processed["n"] >= 1,
    )
    assert cancelled.status is JobStatus.CANCELLED
    # Resume with a different selection → different run_id → empty namespaced dir → no skip.
    resumed = run_batch(
        config_path, _request(source_ids=["note_001", "scan_001"], resume=True)
    )
    assert resumed.run_id != cancelled.run_id
    assert resumed.status is JobStatus.COMPLETED
    assert set(resumed.item_statuses) == {"note_001", "scan_001"}  # both fresh, none skipped


def test_batch_output_is_namespaced_by_run_id(tmp_path: Path) -> None:
    """Distinct selections write to distinct batch-<run_id>/ dirs (finding E)."""
    config_path = _config_at(tmp_path, "out")
    a = run_batch(config_path, _request(source_ids=["note_001"]))
    b = run_batch(config_path, _request(source_ids=["note_002"]))
    assert a.run_id != b.run_id
    assert f"batch-{a.run_id}" in a.summary_path
    assert f"batch-{b.run_id}" in b.summary_path
    assert Path(a.summary_path).exists() and Path(b.summary_path).exists()


def test_batch_config_version_mismatch_fails(tmp_path: Path) -> None:
    result = run_batch(
        _config_at(tmp_path, "out"), _request(config_version="wrong", source_ids=None)
    )
    assert result.status is JobStatus.FAILED
    assert "config_version mismatch" in (result.exception or "")


def test_batch_checkpoint_cadence(tmp_path: Path) -> None:
    # batch_size=1 forces a checkpoint after every item; final result still reconciles.
    result = run_batch(
        _config_at(tmp_path, "out"), _request(source_ids=None, batch_size=1)
    )
    assert result.reconcile.reconciled
    assert len(result.item_statuses) == 5
