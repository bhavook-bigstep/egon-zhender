"""Single-job path: schema + run_single over the frozen manifest."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from libs.jobs import JobRequest, JobStatus, JobType
from pipelines.workstream1_sensitive.job_runner import run_single


@pytest.fixture
def docker_config_path(tmp_path: Path) -> str:
    """A config pointing at the synthetic sample with a temp result dir."""
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    return str(cfg_path)


CONFIG_VERSION = "ws1-0.1.0-poc"


def _request(**kw: object) -> JobRequest:
    kw.setdefault("job_type", JobType.SINGLE)
    kw.setdefault("config_version", CONFIG_VERSION)
    return JobRequest(**kw)  # type: ignore[arg-type]


def test_single_job_flags_one_item(docker_config_path: str) -> None:
    result = run_single(docker_config_path, _request(source_ids=["note_001"]))
    assert result.status is JobStatus.COMPLETED
    assert result.job_type is JobType.SINGLE
    assert result.reconcile.reconciled
    assert result.reconcile.input_count == 1
    assert result.item_statuses == {"note_001": "flagged"}
    # Inline rows are returned for convenience.
    assert len(result.items) == 1
    assert result.items[0].source_id == "note_001"
    assert result.items[0].flag_status.value == "flagged"
    assert "financial" in result.items[0].sensitivity_categories
    # Result set is namespaced per job (no clobber of a batch run).
    assert result.job_id == f"single-{result.run_id}"
    assert Path(result.summary_path).exists()


def test_single_job_streams_stage_events_via_on_event(docker_config_path: str) -> None:
    from libs.audit.ledger import StageEvent

    events: list[StageEvent] = []
    result = run_single(
        docker_config_path, _request(source_ids=["note_001"]), on_event=events.append
    )
    assert result.status is JobStatus.COMPLETED
    assert events, "on_event should receive stage events"
    assert all(isinstance(e, StageEvent) for e in events)
    assert all(e.source_id == "note_001" for e in events)
    assert "extract" in {e.stage for e in events}  # at least the extract stage fired


def test_single_job_unable_item(docker_config_path: str) -> None:
    result = run_single(docker_config_path, _request(source_ids=["unreadable_001"]))
    assert result.status is JobStatus.COMPLETED  # item error is a row, not a job failure
    assert result.item_statuses == {"unreadable_001": "unable_to_process"}
    assert result.items[0].exception_code is not None


def test_single_job_unknown_source_id_fails(docker_config_path: str) -> None:
    result = run_single(docker_config_path, _request(source_ids=["does_not_exist"]))
    assert result.status is JobStatus.FAILED
    assert "not in manifest" in (result.exception or "")


def test_single_job_config_version_mismatch_fails(docker_config_path: str) -> None:
    result = run_single(
        docker_config_path, _request(config_version="wrong", source_ids=["note_001"])
    )
    assert result.status is JobStatus.FAILED
    assert "config_version mismatch" in (result.exception or "")


def test_single_job_requires_source_id(docker_config_path: str) -> None:
    result = run_single(docker_config_path, _request(source_ids=None))
    assert result.status is JobStatus.FAILED
    assert "requires at least one source_id" in (result.exception or "")


def test_single_job_is_reproducible(docker_config_path: str) -> None:
    first = run_single(docker_config_path, _request(source_ids=["note_001"]))
    second = run_single(docker_config_path, _request(source_ids=["note_001"]))
    assert first.run_id == second.run_id  # deterministic over the selected slice


def test_single_job_can_select_multiple(docker_config_path: str) -> None:
    result = run_single(
        docker_config_path, _request(source_ids=["note_001", "note_002"])
    )
    assert result.reconcile.input_count == 2
    assert set(result.item_statuses) == {"note_001", "note_002"}
