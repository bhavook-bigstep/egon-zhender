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


def test_home_is_landing_hero(client: TestClient) -> None:
    """/ is the landing hero: two workstream tools + a top navbar; WS-1 opens /run."""
    r = client.get("/")
    assert r.status_code == 200
    assert 'class="topnav"' in r.text  # reintroduced top navbar
    assert "Workstream 1" in r.text and "Workstream 2" in r.text
    assert 'href="/run"' in r.text  # WS-1 tool opens the console
    assert 'class="sidenav"' not in r.text  # standalone landing, not the console shell


def test_run_page_renders_in_console_shell(client: TestClient) -> None:
    r = client.get("/run")
    assert r.status_code == 200
    assert 'class="topnav"' in r.text  # full-width navbar above the shell
    assert 'class="ez-logo"' in r.text  # navbar carries the Egon Zehnder logo
    assert 'class="shell"' in r.text  # sidebar + main sit BELOW the navbar
    assert 'class="sidenav"' in r.text  # console shell sidebar
    assert 'href="/records"' in r.text  # a sidebar section link
    assert 'id="rows"' in r.text  # the source browser
    assert 'id="notif-btn"' in r.text  # global jobs bell


def test_ws1_browser_is_metadata_only(client: TestClient) -> None:
    r = client.get("/ws1")  # → /run
    assert r.status_code == 200
    assert "Run selected" in r.text  # the smart run control
    assert 'id="rows-pager"' in r.text  # page-based pagination, not "load more"
    # The source browser pages client-side; the page shell carries no source ids.
    assert "note_001" not in r.text
    for token in SENSITIVE_TOKENS:
        assert token not in r.text


def test_source_manifest_api_is_metadata_only(client: TestClient) -> None:
    # The browser now pages via this JSON endpoint; it carries metadata only.
    data = client.get("/api/source/manifest?offset=0&limit=20").json()
    assert data["total"] >= 1
    ids = [it["source_id"] for it in data["items"]]
    assert "note_001" in ids
    for token in SENSITIVE_TOKENS:
        assert token not in json.dumps(data)


def test_live_page_wires_source_id(client: TestClient) -> None:
    r = client.get("/ws1/live?source_id=note_001")
    assert r.status_code == 200
    assert 'data-source-id="note_001"' in r.text
    assert 'id="step-dialog"' in r.text  # per-step detail modal
    assert 'class="steps"' in r.text  # horizontal step flow container


def test_jobs_page_renders(client: TestClient) -> None:
    r = client.get("/jobs")
    assert r.status_code == 200
    assert "Migration" in r.text
    assert "Authorised" in r.text
    assert 'id="jobs-body"' in r.text  # jobs monitor table
    assert 'href="/records"' in r.text  # sidebar section link


def test_jobs_page_has_results_overlay(client: TestClient) -> None:
    """A job's results open in an overlay on the Jobs page (no navigation to Records)."""
    r = client.get("/jobs")
    assert r.status_code == 200
    assert 'id="job-dialog"' in r.text  # the results overlay
    assert 'id="job-dialog-id"' in r.text
    assert 'id="record-dialog"' in r.text  # per-record detail, stacked above
    assert 'id="job-records-body"' in r.text  # scoped, read-only results table
    # approval/adjudication lives only on the Records hub, not in the jobs overlay
    assert 'id="records-review-filter"' not in r.text
    assert "Adjudicate" not in r.text
    # still metadata-only — the overlay scaffold leaks no content
    for token in SENSITIVE_TOKENS:
        assert token not in r.text


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


def test_evaluate_page_renders(client: TestClient) -> None:
    r = client.get("/evaluate")
    assert r.status_code == 200
    assert 'id="eval-body"' in r.text
    assert "expected vs actual" in r.text.lower()
    assert 'href="/evaluate"' in r.text  # sidebar section link


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


def test_records_scoped_to_a_job(client: TestClient) -> None:
    """/jobs/{id} redirects into the Records hub scoped to that job (content-free)."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    jid = submitted["job_id"]
    red = client.get(f"/jobs/{jid}", follow_redirects=False)
    assert red.status_code == 307 and red.headers["location"] == f"/records?job={jid}"
    recs = client.get(f"/api/admin/records?job={jid}").json()["records"]
    assert any(r["source_id"] == "note_001" for r in recs)
    assert not any(tok in json.dumps(recs) for tok in SENSITIVE_TOKENS)  # content-free


def test_record_findings_api_and_drawer(client: TestClient) -> None:
    """Findings for a record come from a content-free API; the Records page has the drawer."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    jid = submitted["job_id"]
    recs = client.get(f"/api/admin/records?job={jid}").json()["records"]
    flagged = next(r for r in recs if r["flag_status"] == "flagged")
    fnd = client.get(f"/api/records/{flagged['source_id']}/findings?job={jid}").json()
    assert fnd["findings"]
    assert all("category" in f and "evidence_str" in f for f in fnd["findings"])
    # Each finding names the evaluator that produced it (who flagged it).
    assert all(f.get("method") for f in fnd["findings"])
    known = {"Presidio", "Presidio (NER)", "Presidio (checksum)", "Semantic screen",
             "LLM", "Custom checksum", "Custom recogniser", "Regex rule"}
    assert all(f["method"] in known for f in fnd["findings"])
    assert not any(tok in json.dumps(fnd) for tok in SENSITIVE_TOKENS)  # location, not value
    assert 'id="record-dialog"' in client.get("/records").text  # detail drawer present


def test_matched_content_is_gated_off_by_default(client: TestClient) -> None:
    """The default app must NOT reveal matched PII: findings are content-free, reveal is empty."""
    submitted = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, submitted["job_id"])
    jid = submitted["job_id"]
    recs = client.get(f"/api/admin/records?job={jid}").json()["records"]
    flagged = next(r for r in recs if r["flag_status"] == "flagged")
    fnd = client.get(f"/api/records/{flagged['source_id']}/findings?job={jid}").json()
    assert not any(tok in json.dumps(fnd) for tok in SENSITIVE_TOKENS)
    rev = client.get(f"/api/jobs/{jid}/reveal?source_id={flagged['source_id']}").json()
    assert rev["spans"] == []  # reveal off by default


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
        # The Records page signals reveal-on; the drawer fetches spans lazily per record.
        assert 'data-reveal="1"' in c.get("/records").text
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
    """Legacy/base paths redirect into the console; /jobs is now a real page."""
    for path, target in [("/live/", "/run"), ("/live", "/run"),
                         ("/admin", "/jobs"), ("/admin/workbook", "/records")]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (303, 307), path
        assert r.headers["location"] == target, path
    assert client.get("/jobs").status_code == 200  # /jobs is the monitor page


def test_live_without_source_redirects_to_run(client: TestClient) -> None:
    r = client.get("/ws1/live", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/run"


def test_unknown_path_renders_branded_404(client: TestClient) -> None:
    r = client.get("/does/not/exist", headers={"accept": "text/html"})
    assert r.status_code == 404
    assert "Page not found" in r.text


def test_unknown_job_redirects_to_records(client: TestClient) -> None:
    red = client.get("/jobs/does-not-exist", follow_redirects=False)
    assert red.status_code == 307
    assert "records?job=does-not-exist" in red.headers["location"]
    assert client.get("/api/admin/records?job=does-not-exist").json()["records"] == []


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
    # Interactive stores rows inline on the job → exercises the inline-items branch.
    recs = client.get(f"/api/admin/records?job={job_id}").json()["records"]
    assert any(r["source_id"] == "note_001" for r in recs)
    assert not any(tok in json.dumps(recs) for tok in SENSITIVE_TOKENS)


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
        # /jobs/{id} redirects into Records; a job with no result yet → empty scoped list.
        assert c.get(f"/jobs/{submitted['job_id']}", follow_redirects=False).status_code == 307
        assert c.get(f"/api/admin/records?job={submitted['job_id']}").json()["records"] == []
        assert c.get("/records").status_code == 200


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
        assert c.get("/api/source/manifest?offset=0").status_code == 200
        assert c.get("/api/source/manifest?offset=100").status_code == 200
    assert calls["n"] == 1  # one manifest read across three paginated requests


def test_recognizers_page_renders(client: TestClient) -> None:
    r = client.get("/recognizers")
    assert r.status_code == 200
    assert 'id="rec-form"' in r.text
    assert 'href="/recognizers"' in r.text  # sidebar section link
    assert 'name="validator"' in r.text  # checksum dropdown
    assert ">iban_mod97<" in r.text  # options come from VALIDATORS (never empty)
    assert ">weighted_modulus<" in r.text  # declarative custom checksum
    assert 'id="wm-params"' in r.text  # its parameter panel (data, not code)


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

    # a checksum-validated recognizer persists its validator (UI now sets this)
    iban = client.post(
        "/api/admin/recognizers",
        json={
            "name": "iban_checksum", "supported_entity": "IBAN_CODE", "category": "financial",
            "regex": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "validator": "iban_mod97",
        },
    )
    assert iban.status_code == 200
    stored = {r["name"]: r for r in client.get("/api/admin/recognizers").json()["recognizers"]}
    assert stored["iban_checksum"]["validator"] == "iban_mod97"
    # an unknown checksum is rejected at the boundary (422 body validation)
    bad_val = client.post(
        "/api/admin/recognizers",
        json={"name": "q", "supported_entity": "Y", "category": "financial",
              "regex": "a", "validator": "crc32"},
    )
    assert bad_val.status_code == 422

    # a declarative weighted_modulus recognizer persists its checksum params
    wm = client.post(
        "/api/admin/recognizers",
        json={"name": "aba", "supported_entity": "ABA_ROUTING", "category": "financial",
              "regex": r"\b\d{9}\b", "validator": "weighted_modulus",
              "checksum": {"mode": "weighted_sum", "modulus": 10, "weights": [3, 7, 1],
                           "align": "left"}},
    )
    assert wm.status_code == 200
    stored_wm = {r["name"]: r for r in client.get("/api/admin/recognizers").json()["recognizers"]}
    assert stored_wm["aba"]["checksum"]["weights"] == [3, 7, 1]
    # weighted_modulus without a checksum spec is rejected (422)
    no_spec = client.post(
        "/api/admin/recognizers",
        json={"name": "bad_wm", "supported_entity": "Z", "category": "financial",
              "regex": "a", "validator": "weighted_modulus"},
    )
    assert no_spec.status_code == 422

    client.delete("/api/admin/recognizers/iban_checksum")
    client.delete("/api/admin/recognizers/aba")

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


def test_review_reverts_to_pending_on_new_version(client: TestClient) -> None:
    """An approval is valid for the version (run_id) it was made against; a later job that
    brings a different run_id for that record reverts the decision to pending."""
    # Version 1: a job over just note_001 → its own run_id.
    a = client.post(
        "/api/jobs",
        json={"job_type": "batch", "config_version": CONFIG_VERSION, "source_ids": ["note_001"]},
    ).json()
    _poll(client, a["job_id"])
    rec_a = {x["source_id"]: x for x in client.get("/api/admin/records").json()["records"]}[
        "note_001"
    ]
    run_a = rec_a["run_id"]

    # Approve that version (run_id recorded with the decision).
    ok = client.post(
        "/api/admin/reviews",
        json={"source_id": "note_001", "job_id": rec_a["job_id"], "run_id": run_a,
              "status": "accepted", "rationale": "ok for v1"},
    )
    assert ok.status_code == 200
    merged = {x["source_id"]: x for x in client.get("/api/admin/records").json()["records"]}
    assert merged["note_001"]["review_status"] == "accepted"
    assert merged["note_001"]["review_superseded"] is False

    # Version 2: a whole-manifest job → note_001 gets a DIFFERENT run_id (selection differs),
    # and this newer job wins in latest-per-record.
    b = client.post(
        "/api/jobs", json={"job_type": "batch", "config_version": CONFIG_VERSION}
    ).json()
    _poll(client, b["job_id"])
    latest = {x["source_id"]: x for x in client.get("/api/admin/records").json()["records"]}[
        "note_001"
    ]
    assert latest["run_id"] != run_a  # a genuinely new version
    assert latest["review_status"] == "pending"  # approval reverted
    assert latest["review_superseded"] is True
    # The prior decision is still in the append-only audit trail.
    assert client.get("/api/admin/reviews").json()["reviews"]["note_001"]["status"] == "accepted"


def test_run_page_controls(client: TestClient) -> None:
    r = client.get("/run")
    assert r.status_code == 200
    assert 'id="run-selected"' in r.text  # one smart run button (batch straight away / dialog)
    assert 'id="run-dialog"' in r.text  # single-item live-vs-queue dialog
    assert 'id="run-live"' in r.text and 'id="run-queue"' in r.text
