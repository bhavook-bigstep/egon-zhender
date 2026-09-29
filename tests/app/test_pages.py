"""Server-rendered pages: render 200 with expected anchors, and leak no content."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import _evidence_str, create_app

CONFIG_VERSION = "ws1-0.1.0-poc"
SENSITIVE_TOKENS = ("ACCT-123456", "salary", "GOVID-AB123456", "passport", "diagnosis")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    app = create_app(str(cfg_path), str(tmp_path / "r.db"), start_worker=True)
    with TestClient(app) as test_client:
        yield test_client


def _poll(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.1)
    raise AssertionError("job did not finish in time")


def test_hero_renders(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Workstream 1" in r.text
    assert 'href="/ws1"' in r.text


def test_ws1_browser_is_metadata_only(client: TestClient) -> None:
    r = client.get("/ws1")
    assert r.status_code == 200
    assert "note_001" in r.text
    assert "Run single" in r.text and "Run batch" in r.text
    # metadata only: no content, no hash/path columns, no sensitive tokens
    for token in SENSITIVE_TOKENS:
        assert token not in r.text


def test_ws1_rows_fragment_renders(client: TestClient) -> None:
    r = client.get("/ws1/rows?offset=0")
    assert r.status_code == 200
    assert "<tr>" in r.text
    assert "rowcheck" in r.text


def test_live_page_wires_source_id(client: TestClient) -> None:
    r = client.get("/ws1/live?source_id=note_001")
    assert r.status_code == 200
    assert 'data-source-id="note_001"' in r.text


def test_admin_page_renders(client: TestClient) -> None:
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Migration monitor" in r.text
    assert "Authorised" in r.text


def test_results_page_after_batch(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    r = client.get(f"/jobs/{submitted['job_id']}")
    assert r.status_code == 200
    assert "Results workbook" in r.text
    assert "Reconciled" in r.text
    assert "note_001" in r.text
    for token in SENSITIVE_TOKENS:
        assert token not in r.text  # workbook shows categories/locations, not content


def test_results_page_not_found(client: TestClient) -> None:
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404
    assert "not found" in r.text.lower()


def test_static_htmx_is_served(client: TestClient) -> None:
    r = client.get("/static/vendor/htmx.min.js")
    assert r.status_code == 200
    assert "htmx" in r.text[:200]


def test_evidence_str_formats_location_only() -> None:
    assert _evidence_str({"page": 3}) == "p3"
    assert _evidence_str({"sheet": "S1", "cell": "B2"}) == "sheet S1, cell B2"
    assert _evidence_str({"char_start": 10, "char_end": 20}) == "chars 10–20"
    assert _evidence_str({"char_start": 10}) == "chars 10–?"
    assert _evidence_str({}) == "—"


def test_results_page_renders_inline_items_from_interactive(client: TestClient) -> None:
    """Interactive run stores rows inline on the job → exercises the items branch."""
    job_id = None
    with client.stream("GET", "/api/interactive/stream?source_id=note_001") as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                msg = json.loads(line[len("data:") :])
                if msg.get("event") == "done":
                    job_id = msg["result"]["job_id"]
                    break
    assert job_id is not None
    r = client.get(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert "note_001" in r.text and "Results workbook" in r.text
    for token in SENSITIVE_TOKENS:
        assert token not in r.text


def test_results_page_job_without_result_renders_200(tmp_path: Path) -> None:
    """A job that exists but hasn't produced a result yet renders (no exception)."""
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    # No worker → the submitted job stays QUEUED with result=None.
    app = create_app(str(cfg_path), str(tmp_path / "r.db"), start_worker=False)
    with TestClient(app) as c:
        submitted = c.post(
            "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
        ).json()
        r = c.get(f"/jobs/{submitted['job_id']}")
    assert r.status_code == 200
    assert "No rows yet" in r.text
