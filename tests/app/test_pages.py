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
    assert 'id="notif-btn"' in r.text  # global jobs notification button in the navbar


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
    assert 'id="step-dialog"' in r.text  # per-step detail modal
    assert 'class="steps"' in r.text  # horizontal step flow container


def test_admin_page_renders(client: TestClient) -> None:
    r = client.get("/admin")
    assert r.status_code == 200
    assert "Migration" in r.text
    assert "Authorised" in r.text
    assert 'id="jobs-body"' in r.text  # Jobs sub-page
    assert 'href="/admin/workbook"' in r.text  # tab to the Workbook sub-page


def test_admin_workbook_page_renders(client: TestClient) -> None:
    r = client.get("/admin/workbook")
    assert r.status_code == 200
    assert 'id="records-body"' in r.text
    assert "Processed records" in r.text
    assert "records/export?fmt=xlsx" in r.text  # download link


def test_admin_records_export_formats(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])

    xlsx = client.get("/api/admin/records/export?fmt=xlsx")
    assert xlsx.status_code == 200
    assert "spreadsheetml.sheet" in xlsx.headers["content-type"]
    assert "attachment" in xlsx.headers["content-disposition"]

    csv_r = client.get("/api/admin/records/export?fmt=csv")
    assert "text/csv" in csv_r.headers["content-type"]
    assert "source_id" in csv_r.text and "note_001" in csv_r.text
    for token in SENSITIVE_TOKENS:
        assert token not in csv_r.text  # export is content-free (no matched values)

    jsonl = client.get("/api/admin/records/export?fmt=jsonl")
    assert "ndjson" in jsonl.headers["content-type"]
    assert jsonl.text.strip().count("\n") == 4  # 5 records → 5 lines


def test_admin_eval_page_renders(client: TestClient) -> None:
    r = client.get("/admin/eval")
    assert r.status_code == 200
    assert 'id="eval-body"' in r.text
    assert "expected vs actual" in r.text.lower()
    assert 'href="/admin/eval"' in r.text  # the Evaluate tab


def test_admin_eval_api_against_matching_truth(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eval scores the sample run against a golden truth covering the sample ids."""
    (tmp_path / "manifest.jsonl").write_text(
        '{"source_id":"note_001","expected_flag_status":"flagged",'
        '"expected_categories":["financial"],"scanned":false,"scan_severity":null}\n'
        '{"source_id":"note_002","expected_flag_status":"not_flagged",'
        '"expected_categories":[],"scanned":false,"scan_severity":null}\n',
        encoding="utf-8",
    )
    (tmp_path / "labels.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("WS1_GOLDEN_DIR", str(tmp_path))

    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])

    rep = client.get("/api/admin/eval")
    body = rep.json()
    assert body["counts"]["evaluated"] == 2  # only note_001 + note_002 have truth
    assert body["counts"]["flag_tp"] == 1 and body["counts"]["flag_tn"] == 1
    assert body["flagging"]["recall"] == 1.0 and body["flagging"]["precision"] == 1.0
    rows = {r["source_id"]: r for r in body["rows"]}
    assert rows["note_001"]["flag_match"] and rows["note_002"]["flag_match"]
    for token in SENSITIVE_TOKENS:
        assert token not in rep.text  # content-free (no matched values)


def test_admin_records_latest_per_input(client: TestClient) -> None:
    """The records workbook has exactly one (deduplicated) row per input, latest job."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    recs = client.get("/api/admin/records").json()["records"]
    ids = [x["source_id"] for x in recs]
    assert len(ids) == len(set(ids)) == 5  # one per input, deduplicated across jobs
    assert all("job_id" in x and "flag_status" in x for x in recs)
    # Re-run one item interactively → its record points at the newer job, still 5 records.
    with client.stream("GET", "/api/interactive/stream?source_id=note_001") as resp:
        for line in resp.iter_lines():
            if line.startswith("data:") and '"done"' in line:
                break
    recs2 = {x["source_id"]: x for x in client.get("/api/admin/records").json()["records"]}
    assert len(recs2) == 5
    assert recs2["note_001"]["job_id"] != submitted["job_id"]  # newer job wins


def test_results_page_after_batch(client: TestClient) -> None:
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    r = client.get(f"/jobs/{submitted['job_id']}")
    assert r.status_code == 200
    assert "Workbook" in r.text
    assert "Reconciled" in r.text
    assert "note_001" in r.text
    for token in SENSITIVE_TOKENS:
        assert token not in r.text  # workbook shows categories/locations, not content


def test_results_page_findings_open_in_dialog(client: TestClient) -> None:
    """Findings render as a modal dialog (opened by a per-row button), not a nested table."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    r = client.get(f"/jobs/{submitted['job_id']}")
    assert r.status_code == 200
    assert 'data-dialog="finding-dlg-' in r.text  # per-row opener button
    assert "<dialog" in r.text and "finding-card" in r.text  # server-rendered modal
    for token in SENSITIVE_TOKENS:
        assert token not in r.text  # dialog shows reason template + location only


def test_matched_content_is_gated_off_by_default(client: TestClient) -> None:
    """The default app must NOT reveal matched PII spans (production-safe default)."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    r = client.get(f"/jobs/{submitted['job_id']}")
    assert "Matched content" not in r.text
    for token in SENSITIVE_TOKENS:
        assert token not in r.text


def test_matched_content_reveals_when_opted_in(tmp_path: Path) -> None:
    """With reveal_matches=True, the review dialog shows the matched span (synthetic PoC)."""
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    app = create_app(
        str(cfg_path), str(tmp_path / "r.db"), start_worker=True, reveal_matches=True
    )
    with TestClient(app) as c:
        submitted = c.post(
            "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
        ).json()
        _poll(c, submitted["job_id"])
        r = c.get(f"/jobs/{submitted['job_id']}")
        # Page renders WITHOUT eager reveal (no re-extraction of every doc): no span inline.
        assert "fc-match-slot" in r.text and "<mark>" not in r.text
        # Reveal is lazy per-record: the dialog fetches one record's span on open.
        flagged = next(
            row["source_id"]
            for row in c.get("/api/admin/records").json()["records"]
            if row["flag_status"] == "flagged"
        )
        rev = c.get(f"/api/jobs/{submitted['job_id']}/reveal?source_id={flagged}").json()
    assert rev["spans"] and rev["spans"][0]["char_match"]  # matched span served on demand


def test_reveal_endpoint_gated_off_by_default(client: TestClient) -> None:
    """Without reveal enabled, the per-record reveal endpoint returns no spans."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    body = client.get(f"/api/jobs/{submitted['job_id']}/reveal?source_id=note_001").json()
    assert body["spans"] == []


def _stream_detect_record(c: TestClient, source_id: str) -> dict:
    detect = None
    with c.stream("GET", f"/api/interactive/stream?source_id={source_id}") as r:
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            msg = json.loads(line[len("data:") :])
            if msg.get("event") == "stage" and msg["stage"] == "detect":
                detect = msg
            if msg.get("event") == "done":
                break
    assert detect is not None and detect["records"]
    return detect


def test_step_detect_records_carry_no_value_by_default(client: TestClient) -> None:
    detect = _stream_detect_record(client, "note_001")
    assert all("value" not in rec for rec in detect["records"])  # location only, no value


def test_step_detect_records_reveal_value_when_opted_in(tmp_path: Path) -> None:
    """With reveal on, each detection record carries the matched value (synthetic PoC)."""
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    app = create_app(
        str(cfg_path), str(tmp_path / "r.db"), start_worker=True, reveal_matches=True
    )
    with TestClient(app) as c:
        detect = _stream_detect_record(c, "note_001")
    assert any("value" in rec for rec in detect["records"])
    assert any(rec.get("value") == "ACCT-123456" for rec in detect["records"])


def test_reveal_enabled_via_config_flag(tmp_path: Path) -> None:
    """`reveal_matched_content: true` in the config turns reveal on (no env/param needed)."""
    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    base["reveal_matched_content"] = True
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    app = create_app(str(cfg_path), str(tmp_path / "r.db"), start_worker=True)  # no param/env
    with TestClient(app) as c:
        detect = _stream_detect_record(c, "note_001")
    assert any(rec.get("value") == "ACCT-123456" for rec in detect["records"])


def test_base_paths_redirect(client: TestClient) -> None:
    """/jobs/ and /live/ (no id/param) redirect instead of raw 404/422."""
    for path, target in [("/jobs/", "/admin"), ("/jobs", "/admin"),
                         ("/live/", "/ws1"), ("/live", "/ws1")]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (303, 307), path
        assert r.headers["location"] == target, path


def test_live_without_source_redirects_to_browser(client: TestClient) -> None:
    r = client.get("/ws1/live", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/ws1"


def test_unknown_path_renders_branded_404(client: TestClient) -> None:
    r = client.get("/does/not/exist", headers={"accept": "text/html"})
    assert r.status_code == 404
    assert "Page not found" in r.text


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
    assert "note_001" in r.text and "Workbook" in r.text
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


def test_manifest_fetched_once_across_pagination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The frozen manifest is fetched once; paginating the source browser never re-reads
    the source (matters for the Databricks backend — no repeated manifest downloads)."""
    import app.main as appmain

    base = yaml.safe_load(Path("config/ws1.yaml").read_text(encoding="utf-8"))
    base["output"]["result_dir"] = str(tmp_path / "out")
    cfg_path = tmp_path / "ws1.yaml"
    cfg_path.write_text(yaml.safe_dump(base), encoding="utf-8")

    calls = {"n": 0}
    real_build_reader = appmain.build_reader

    def counting_build_reader(cfg: object) -> object:
        calls["n"] += 1
        return real_build_reader(cfg)  # type: ignore[arg-type]

    monkeypatch.setattr(appmain, "build_reader", counting_build_reader)

    app = create_app(str(cfg_path), str(tmp_path / "r.db"), start_worker=False)
    with TestClient(app) as c:
        assert c.get("/ws1").status_code == 200
        assert c.get("/ws1/rows?offset=100").status_code == 200
        assert c.get("/api/source/manifest?offset=0").status_code == 200
    assert calls["n"] == 1  # one manifest read across three paginated requests


def test_recognizers_page_renders(client: TestClient) -> None:
    r = client.get("/admin/recognizers")
    assert r.status_code == 200
    assert 'id="rec-form"' in r.text
    assert 'href="/admin/recognizers"' in r.text  # the Recognizers tab


def test_recognizers_crud_api(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Add / list / delete custom recognizers via the admin API (validated, persisted)."""
    monkeypatch.setenv("WS1_RECOGNIZERS_FILE", str(tmp_path / "rec.json"))
    assert client.get("/api/admin/recognizers").json()["recognizers"] == []

    ok = client.post(
        "/api/admin/recognizers",
        json={
            "name": "swift", "supported_entity": "SWIFT_BIC", "category": "financial",
            "regex": r"\b[A-Z]{4}[A-Z0-9]{4,7}\b", "score": 0.3, "context": ["swift"],
        },
    )
    assert ok.status_code == 200
    assert ok.json()["recognizers"][0]["supported_entity"] == "SWIFT_BIC"
    # persisted across requests
    assert client.get("/api/admin/recognizers").json()["recognizers"][0]["name"] == "swift"

    # category must be in the taxonomy → 400
    bad_cat = client.post(
        "/api/admin/recognizers",
        json={"name": "x", "supported_entity": "Y", "category": "nope", "regex": "a"},
    )
    assert bad_cat.status_code == 400
    # duplicate name → 400
    dup = client.post(
        "/api/admin/recognizers",
        json={
            "name": "swift", "supported_entity": "SWIFT_BIC",
            "category": "financial", "regex": "a",
        },
    )
    assert dup.status_code == 400
    # invalid regex → 422 (body validation)
    bad_re = client.post(
        "/api/admin/recognizers",
        json={"name": "z", "supported_entity": "Y", "category": "financial", "regex": "(["},
    )
    assert bad_re.status_code == 422

    client.delete("/api/admin/recognizers/swift")
    assert client.get("/api/admin/recognizers").json()["recognizers"] == []


def test_workbook_page_has_adjudication_controls(client: TestClient) -> None:
    r = client.get("/admin/workbook")
    assert r.status_code == 200
    assert 'id="records-sort"' in r.text and 'id="records-review-filter"' in r.text


def test_review_adjudication_flow(client: TestClient) -> None:
    """Record a reviewer decision; it surfaces in records + reviews + export, content-free."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    recs = client.get("/api/admin/records").json()["records"]
    assert recs and all(r["review_status"] == "pending" for r in recs)  # default
    sid = recs[0]["source_id"]

    ok = client.post(
        "/api/admin/reviews",
        json={"source_id": sid, "job_id": recs[0]["job_id"],
              "status": "accepted", "rationale": "looks correct"},
    )
    assert ok.status_code == 200 and ok.json()["review"]["status"] == "accepted"

    merged = {x["source_id"]: x for x in client.get("/api/admin/records").json()["records"]}
    assert merged[sid]["review_status"] == "accepted"
    assert merged[sid]["reviewer"] == "operator"
    assert client.get("/api/admin/reviews").json()["reviews"][sid]["status"] == "accepted"

    bad_status = client.post("/api/admin/reviews", json={"source_id": sid, "status": "nope"})
    assert bad_status.status_code == 400
    no_id = client.post("/api/admin/reviews", json={"status": "accepted"})
    assert no_id.status_code == 400

    exp = client.get("/api/admin/records/export?fmt=csv")
    assert "review_status" in exp.text and "rationale" in exp.text and "looks correct" in exp.text
    for token in SENSITIVE_TOKENS:
        assert token not in exp.text  # reviewer text only, no source content
