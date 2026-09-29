"""FastAPI service: metadata-only surface, submit/poll, results, admin, SSE."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app

CONFIG_VERSION = "ws1-0.1.0-poc"
SENSITIVE_TOKENS = ("ACCT-123456", "salary", "GOVID-AB123456", "passport")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    app = create_app(str(cfg_path), str(tmp_path / "r.db"), start_worker=True)
    with TestClient(app) as test_client:  # runs startup (worker) + shutdown
        yield test_client


def _poll(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish in time")


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_source_manifest_is_metadata_only(client: TestClient) -> None:
    response = client.get("/api/source/manifest")
    body = response.json()
    assert body["total"] == 5
    item = body["items"][0]
    assert "content_hash" not in item  # excluded
    assert "text" not in item and "content" not in item
    for token in SENSITIVE_TOKENS:
        assert token not in response.text


def test_submit_poll_results_and_summary(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    job = _poll(client, submitted["job_id"])
    assert job["status"] == "completed"

    results = client.get(f"/api/jobs/{submitted['job_id']}/results")
    body = results.json()
    assert body["reconcile"]["reconciled"] is True
    assert len(body["rows"]) == 5
    for token in SENSITIVE_TOKENS:
        assert token not in results.text  # no content leak in rows

    summary = client.get("/api/admin/summary").json()
    assert summary["authorised"] == 5
    assert summary["processed"] == 5


def test_submit_config_mismatch(client: TestClient) -> None:
    job = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": "wrong"}
    ).json()
    assert job["status"] == "failed"


def test_interactive_stream_yields_events(client: TestClient) -> None:
    events = []
    with client.stream("GET", "/api/interactive/stream?source_id=note_001") as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :]))
                if events[-1].get("event") == "done":
                    break
    kinds = {e["event"] for e in events}
    assert "stage" in kinds and "done" in kinds


def test_retry_failed_nothing_to_retry(client: TestClient) -> None:
    response = client.post("/api/jobs/does-not-exist/retry-failed")
    assert response.json() == {"error": "nothing to retry"}


def test_get_unknown_job_returns_error(client: TestClient) -> None:
    assert client.get("/api/jobs/does-not-exist").json() == {"error": "not found"}


def test_admin_stream_smoke(client: TestClient) -> None:
    with client.stream("GET", "/api/admin/stream?max_events=1") as response:
        payloads = [
            json.loads(line[len("data:") :])
            for line in response.iter_lines()
            if line.startswith("data:")
        ]
    assert payloads and payloads[0]["event"] == "summary"
