"""FastAPI service for WS-1 (PoC).

API-first: the CLI and this API share `JobService` + the registry. All responses are
METADATA ONLY — never document content or raw identifiers. Local/no-auth (PoC); bind to
loopback. The frontend pages (operator flow + admin) are added in the next wave; this
module is the backend API + SSE.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from starlette.exceptions import HTTPException as StarletteHTTPException

from libs.config import load_ws1_config
from libs.eval.golden import DEFAULT_GOLDEN_DIR, load_golden_truth
from libs.eval.metrics import evaluate
from libs.jobs import Job, JobRequest
from libs.recognizers_store import (
    StoredRecognizer,
    load_recognizers,
    save_recognizers,
)
from libs.registry import JobRegistry
from libs.review_store import VALID_STATUSES, ReviewStore
from libs.schemas import Finding, ManifestEntry, ScoreType, Ws1Summary
from pipelines.workstream1_sensitive.extract_engine import build_extraction_engine
from pipelines.workstream1_sensitive.ingest import ingest
from pipelines.workstream1_sensitive.job_service import JobService
from pipelines.workstream1_sensitive.runner import build_reader
from pipelines.workstream1_sensitive.worker import Worker

_APP_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _APP_DIR.parent
_PAGE_SIZE = 100
_MATCH_CONTEXT_CHARS = 48


def _load_dotenv(path: Path = _REPO_ROOT / ".env") -> None:
    """Load repo-root .env into the environment so `uvicorn app.main:app` needs no env
    prefix. Values already set in the real environment win (CLI/shell override .env), and
    a missing file is a no-op. Stdlib only — .env is git-ignored (may hold a reveal flag)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


# Auto-load .env when serving, but never under pytest — tests set their own env and must
# not inherit a developer's local .env (e.g. a WS1_SHOW_MATCHED_CONTENT reveal flag).
if "pytest" not in sys.modules:
    _load_dotenv()

# ws1_item_summary export columns (response §3.4 order) + latest-job provenance.
_EXPORT_COLUMNS = [
    "source_id", "content_type", "flag_status", "sensitivity_categories", "reason_summary",
    "processing_status", "calibration_status", "strongest_band", "strongest_score_type",
    "strongest_score", "exception_code", "snapshot_id", "content_hash", "run_id",
    "config_version", "author", "datetime", "linked_executive", "linked_project", "job_id",
    "review_status", "reviewer", "rationale", "decided_at",  # human adjudication (6a)
]


def _export_cell(record: dict[str, Any], column: str) -> Any:
    value = record.get(column)
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return "" if value is None else value


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _evidence_str(loc: dict[str, Any]) -> str:
    """Render an evidence location (page/sheet/cell/offset) — never any content."""
    parts = []
    if loc.get("page") is not None:
        parts.append(f"p{loc['page']}")
    if loc.get("sheet"):
        parts.append(f"sheet {loc['sheet']}")
    if loc.get("cell"):
        parts.append(f"cell {loc['cell']}")
    if loc.get("char_start") is not None:
        parts.append(f"chars {loc['char_start']}–{loc.get('char_end', '?')}")
    return ", ".join(parts) or "—"


_CHAR_LOC_RE = re.compile(r"chars (\d+)-(\d+)")


def _extract_source_text(config_path: str, source_id: str) -> str | None:
    """Re-derive one item's extracted text from the read-only source (for gated reveal)."""
    cfg = load_ws1_config(config_path)
    reader = build_reader(cfg)
    engine = build_extraction_engine(cfg.extract)
    entry = next((e for e in reader.list_manifest() if e.source_id == source_id), None)
    if entry is None:
        return None
    try:
        return engine.extract(entry, ingest(reader, entry)).text
    except Exception:  # extraction may fail — then no value is revealed
        return None


def _reveal_record_values(records: list[dict[str, Any]], text: str | None) -> None:
    """PoC/gated: add the matched `value` to each detection record with char offsets.

    The value is sliced live from the read-only source `text` and NOT persisted anywhere
    (the pipeline records + ledger stay content-free). Off unless reveal is enabled.
    """
    if not text:
        return
    for record in records:
        match = _CHAR_LOC_RE.search(str(record.get("location", "")))
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            record["value"] = text[start:end]


def _latest_per_record(registry: JobRegistry) -> list[dict[str, Any]]:
    """Consolidated view: the LATEST processed row per input source_id across all jobs.

    Newest job wins (by updated_at). Content-free — Ws1Summary carries flag status,
    categories, score type/band, calibration, exception; never matched content.
    """
    jobs = sorted(
        registry.list(limit=500),
        key=lambda j: j.updated_at or j.created_at,
        reverse=True,
    )
    seen: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if job.result is None:
            continue
        rows, _ = _load_rows_findings(job)
        for row in rows:
            if row.source_id in seen:
                continue  # a newer job already recorded this record
            record = row.model_dump(mode="json")
            record["job_id"] = job.job_id
            record["job_updated_at"] = job.updated_at
            seen[row.source_id] = record
    return [seen[sid] for sid in sorted(seen)]


def _load_rows_findings(job: Job) -> tuple[list[Ws1Summary], list[Finding]]:
    """Read a job's output rows + findings (inline for single, from disk for batch)."""
    rows: list[Ws1Summary] = []
    findings: list[Finding] = []
    result = job.result
    if result is None:
        return rows, findings
    if result.items:
        rows = list(result.items)
    elif result.summary_path and Path(result.summary_path).exists():
        rows = [
            Ws1Summary.model_validate_json(line)
            for line in Path(result.summary_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if result.findings:
        findings = list(result.findings)
    elif result.findings_path and Path(result.findings_path).exists():
        findings = [
            Finding.model_validate_json(line)
            for line in Path(result.findings_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return rows, findings


def create_app(
    config_path: str | None = None,
    registry_db: str | None = None,
    start_worker: bool = True,
    reveal_matches: bool | None = None,
) -> FastAPI:
    config_path = config_path or os.environ.get("WS1_API_CONFIG", "config/ws1.yaml")
    registry_db = registry_db or os.environ.get("WS1_REGISTRY_DB", "poc/registry.db")
    # Off by default (production-safe). Opt-in reveals the matched value in the review UI,
    # re-derived live from the read-only source and never persisted (Contracts 2 & 3).
    # Precedence: explicit arg > WS1_SHOW_MATCHED_CONTENT env > config.reveal_matched_content.
    if reveal_matches is None:
        env_flag = os.environ.get("WS1_SHOW_MATCHED_CONTENT")
        if env_flag is not None:
            reveal_matches = env_flag == "1"
        else:
            reveal_matches = load_ws1_config(config_path).reveal_matched_content

    registry = JobRegistry(registry_db)
    reviews = ReviewStore(registry_db)  # own tables in the same DB file
    service = JobService(config_path, registry)
    worker = Worker(service, registry) if start_worker else None

    def _records_with_reviews() -> list[dict[str, Any]]:
        """Latest processed row per record, each merged with its current review decision."""
        review_by_id = reviews.all()
        rows = _latest_per_record(registry)
        for row in rows:
            decision = review_by_id.get(row["source_id"])
            row["review_status"] = decision["status"] if decision else "pending"
            row["reviewer"] = decision["reviewer"] if decision else None
            row["rationale"] = decision["rationale"] if decision else None
            row["decided_at"] = decision["decided_at"] if decision else None
        return rows

    _manifest_cache: dict[str, list[ManifestEntry]] = {}

    def _manifest() -> list[ManifestEntry]:
        # The manifest is frozen for the life of a run (Contract 4), so fetch + parse it once
        # and slice from memory for pagination. For the Databricks backend this turns every
        # /ws1 page load and every "Load more" from a full manifest.jsonl download off the UC
        # volume into a single cached read (performance.md: no repeated full-corpus-metadata
        # reads, no N+1 source reads). Also backs the admin SSE authorised count.
        if "entries" not in _manifest_cache:
            cfg = load_ws1_config(config_path)
            _manifest_cache["entries"] = build_reader(cfg).list_manifest()
        return _manifest_cache["entries"]

    def _authorised() -> int:
        return len(_manifest())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        registry.reconcile_stale_running()  # clear jobs orphaned by a prior restart
        if worker is not None:
            worker.start()
        # Pre-warm the context (load SBERT, cache the manifest) off the request path so the
        # FIRST live run starts fast instead of paying the ~18s cold model load on click.
        threading.Thread(target=service.warm, daemon=True).start()
        yield
        if worker is not None:
            worker.stop()
        registry.close()
        reviews.close()

    app = FastAPI(title="WS-1 PoC service", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))
    # Cache-bust CSS/JS: version the asset URLs by their newest mtime so a restart after an
    # edit always makes the browser refetch (no stale app.css/app.js served from cache).
    _static = _APP_DIR / "static"
    _asset_paths = [_static / "app.css", _static / "app.js"]
    _asset_ver = str(max((p.stat().st_mtime_ns for p in _asset_paths if p.exists()), default=0))
    templates.env.globals["asset_ver"] = _asset_ver

    @app.exception_handler(StarletteHTTPException)
    async def _not_found(request: Request, exc: StarletteHTTPException) -> Any:
        # Branded 404 page for browser navigation; JSON for API clients.
        if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                request=request, name="notfound.html", context={}, status_code=404
            )
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    def _config_meta() -> dict[str, Any]:
        cfg = load_ws1_config(config_path)
        return {
            "config_version": cfg.config_version,
            "inference_local": cfg.inference.is_local,
            "model_version": cfg.inference.model_version,
            "approval_written": cfg.inference.approval_written,
        }

    # --- pages (server-rendered; UI is a client of the same API) ---

    @app.get("/", response_class=HTMLResponse)
    def page_hero(request: Request) -> Any:
        return templates.TemplateResponse(
            request=request, name="hero.html", context=_config_meta()
        )

    @app.get("/ws1", response_class=HTMLResponse)
    def page_ws1(request: Request) -> Any:
        entries = _manifest()  # cached; sliced in memory, not re-fetched per page
        window = entries[:_PAGE_SIZE]
        next_offset = _PAGE_SIZE if len(entries) > _PAGE_SIZE else None
        return templates.TemplateResponse(
            request=request,
            name="ws1.html",
            context={
                **_config_meta(),
                "items": window,
                "total": len(entries),
                "loaded": len(window),
                "next_offset": next_offset,
            },
        )

    @app.get("/ws1/rows", response_class=HTMLResponse)
    def page_ws1_rows(request: Request, offset: int = 0) -> Any:
        """HTMX fragment: the next page of source rows (+ an OOB load-more button)."""
        entries = _manifest()  # cached; a "Load more" click never re-hits the source
        offset = max(0, offset)
        window = entries[offset : offset + _PAGE_SIZE]
        nxt = offset + _PAGE_SIZE
        next_offset = nxt if len(entries) > nxt else None
        return templates.TemplateResponse(
            request=request,
            name="_rows.html",
            context={
                "items": window,
                "total": len(entries),
                "loaded": min(nxt, len(entries)),
                "next_offset": next_offset,
                "oob": True,
            },
        )

    @app.get("/ws1/live", response_class=HTMLResponse)
    def page_live(request: Request, source_id: str | None = None) -> Any:
        if not source_id:  # no item selected → send back to the browser to pick one
            return RedirectResponse("/ws1", status_code=303)
        return templates.TemplateResponse(
            request=request, name="live.html", context={"source_id": source_id}
        )

    # Friendly redirects for base paths that carry no id/param (avoid raw 404/422).
    @app.get("/jobs")
    @app.get("/jobs/")
    def jobs_redirect() -> Any:
        return RedirectResponse("/admin", status_code=303)

    @app.get("/live")
    @app.get("/live/")
    def live_redirect() -> Any:
        return RedirectResponse("/ws1", status_code=303)

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def page_results(request: Request, job_id: str) -> Any:
        job = registry.get(job_id)
        if job is None:
            return templates.TemplateResponse(
                request=request,
                name="results.html",
                context={"job": None, "rows": [], "findings_by_source": {}, "reconcile": None},
                status_code=404,
            )
        rows, findings = _load_rows_findings(job)
        findings_by_source: dict[str, list[dict[str, Any]]] = {}
        for finding in findings:
            dumped = finding.model_dump(mode="json")
            dumped["evidence_str"] = _evidence_str(dumped["evidence_location"])
            # SIMILARITY is a routing/prioritisation signal, excluded from the flag decision
            # (score.py); mark it so the workbook can separate it from flag-driving findings.
            dumped["routing_only"] = dumped["score_type"] == ScoreType.SIMILARITY.value
            findings_by_source.setdefault(finding.source_id, []).append(dumped)
        # Reveal is LAZY (per-record, on dialog open) — never eager here. Eagerly re-deriving
        # matched content for every finding would re-download + re-extract every document from
        # source at render time (minutes for a 48-item batch). The dialog fetches one record's
        # spans from /api/jobs/{id}/reveal on demand.
        return templates.TemplateResponse(
            request=request,
            name="results.html",
            context={
                "job": job,
                "rows": rows,
                "findings_by_source": findings_by_source,
                "reconcile": job.result.reconcile if job.result else None,
                "reveal_enabled": reveal_matches,
            },
        )

    @app.get("/api/jobs/{job_id}/reveal")
    def job_reveal(job_id: str, source_id: str) -> dict[str, Any]:
        """Gated, lazy matched-content reveal for ONE record (opened in the review dialog).

        Re-derives the span LIVE from the read-only source (one document) via the warm
        context — never persisted (Contracts 2 & 3). Off unless reveal is enabled.
        """
        if not reveal_matches:
            return {"source_id": source_id, "spans": []}
        job = registry.get(job_id)
        if job is None:
            return {"source_id": source_id, "spans": []}
        _, findings = _load_rows_findings(job)
        src_findings = [f for f in findings if f.source_id == source_id]
        if not src_findings:
            return {"source_id": source_id, "spans": []}
        ctx = service.context()  # warm: manifest cached, engine built (no re-download)
        entry = next(
            (e for e in ctx.reader.list_manifest() if e.source_id == source_id), None
        )
        text: str | None = None
        if entry is not None:
            try:
                text = ctx.extraction_engine.extract(entry, ingest(ctx.reader, entry)).text
            except Exception:  # extraction may fail — then no span is revealed
                text = None
        spans: list[dict[str, Any]] = []
        if text:
            for finding in src_findings:
                loc = finding.evidence_location
                start, end = loc.char_start, loc.char_end
                if start is None or end is None or start >= len(text):
                    continue
                end = min(end, len(text))
                spans.append(
                    {
                        "finding_id": finding.finding_id,
                        "char_pre": text[max(0, start - _MATCH_CONTEXT_CHARS) : start],
                        "char_match": text[start:end],
                        "char_post": text[end : end + _MATCH_CONTEXT_CHARS],
                    }
                )
        return {"source_id": source_id, "spans": spans}

    @app.get("/admin", response_class=HTMLResponse)
    def page_admin(request: Request) -> Any:
        summary = registry.migration_summary(_authorised())
        jobs = registry.list(limit=50)
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "config_version": _config_meta()["config_version"],
                "summary": summary,
                "jobs": jobs,
            },
        )

    @app.get("/admin/workbook", response_class=HTMLResponse)
    def page_admin_workbook(request: Request) -> Any:
        summary = registry.migration_summary(_authorised())
        return templates.TemplateResponse(
            request=request,
            name="admin_workbook.html",
            context={
                "config_version": _config_meta()["config_version"],
                "summary": summary,
            },
        )

    @app.get("/admin/eval", response_class=HTMLResponse)
    def page_admin_eval(request: Request) -> Any:
        summary = registry.migration_summary(_authorised())
        return templates.TemplateResponse(
            request=request,
            name="admin_eval.html",
            context={
                "config_version": _config_meta()["config_version"],
                "summary": summary,
            },
        )

    @app.get("/admin/recognizers", response_class=HTMLResponse)
    def page_admin_recognizers(request: Request) -> Any:
        summary = registry.migration_summary(_authorised())
        return templates.TemplateResponse(
            request=request,
            name="admin_recognizers.html",
            context={
                "config_version": _config_meta()["config_version"],
                "summary": summary,
                "categories": load_ws1_config(config_path).taxonomy.categories,
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/source/manifest")
    def source_manifest(offset: int = 0, limit: int = 100) -> dict[str, Any]:
        """Metadata-only view of authorised items (no content)."""
        entries = _manifest()  # cached; paging never re-downloads the manifest
        offset = max(0, offset)
        window = entries[offset : offset + limit]
        # Exclude content_hash (internal reconciliation) and path (source-layout
        # detail the operator does not need) — reference items by source_id only.
        return {
            "total": len(entries),
            "offset": offset,
            "items": [e.model_dump(exclude={"content_hash", "path"}) for e in window],
        }

    @app.post("/api/jobs")
    def submit_job(request: JobRequest) -> Job:
        return service.submit(request)

    @app.get("/api/jobs")
    def list_jobs(limit: int = 100) -> list[Job]:
        return registry.list(limit=limit)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> Job | dict[str, str]:
        job = registry.get(job_id)
        return job if job is not None else {"error": "not found"}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, bool]:
        return {"cancelled": service.cancel(job_id)}

    @app.post("/api/jobs/{job_id}/retry-failed")
    def retry_failed(job_id: str) -> Job | dict[str, str]:
        job = service.retry_failed(job_id)
        return job if job is not None else {"error": "nothing to retry"}

    @app.get("/api/jobs/{job_id}/results")
    def job_results(job_id: str) -> dict[str, Any]:
        job = registry.get(job_id)
        if job is None or job.result is None:
            return {"error": "no results"}
        # Reuse the one row-loading path (inline items, else summary_path). content_hash is
        # intentionally present in a result row (post-processing provenance/reconciliation),
        # unlike the pre-processing manifest browse which drops it.
        rows, _ = _load_rows_findings(job)
        return {
            "reconcile": job.result.reconcile.model_dump(),
            "rows": [row.model_dump(mode="json") for row in rows],
        }

    @app.get("/api/interactive/stream")
    def interactive_stream(source_id: str) -> StreamingResponse:
        cfg = load_ws1_config(config_path)
        request = JobRequest(
            job_type="single",  # type: ignore[arg-type]
            config_version=cfg.config_version,
            source_ids=[source_id],
        )

        text_cache: dict[str, str | None] = {}

        def gen() -> Iterator[str]:
            for event in service.run_interactive(request):
                if reveal_matches and event.get("event") == "stage" and event.get("records"):
                    if "t" not in text_cache:
                        text_cache["t"] = _extract_source_text(config_path, source_id)
                    _reveal_record_values(event["records"], text_cache["t"])
                yield _sse(event)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/admin/summary")
    def admin_summary() -> dict[str, Any]:
        return registry.migration_summary(_authorised()).model_dump()

    @app.get("/api/admin/records")
    def admin_records() -> dict[str, Any]:
        """Latest processed row per input record (deduplicated), with review state."""
        return {"records": _records_with_reviews()}

    @app.get("/api/admin/reviews")
    def list_reviews() -> dict[str, Any]:
        """Current adjudication decision per source_id."""
        return {"reviews": reviews.all()}

    @app.post("/api/admin/reviews")
    def add_review(decision: dict[str, Any]) -> Response:
        """Record a reviewer decision (accept/reject/needs_info) + rationale, audit-logged."""
        source_id = str(decision.get("source_id") or "").strip()
        status = str(decision.get("status") or "").strip()
        if not source_id:
            return JSONResponse({"error": "source_id is required"}, status_code=400)
        if status not in VALID_STATUSES:
            return JSONResponse(
                {"error": f"status must be one of {list(VALID_STATUSES)}"}, status_code=400
            )
        row = reviews.set_decision(
            source_id=source_id,
            job_id=str(decision.get("job_id") or ""),
            status=status,
            reviewer=str(decision.get("reviewer") or "operator"),
            rationale=str(decision.get("rationale") or ""),
            calibrated_score=decision.get("calibrated_score"),
        )
        return JSONResponse({"review": row})

    @app.get("/api/admin/eval")
    def admin_eval() -> dict[str, Any]:
        """Expected-vs-actual evaluation against the golden truth (content-free)."""
        golden_dir = os.environ.get("WS1_GOLDEN_DIR", str(DEFAULT_GOLDEN_DIR))
        truth = load_golden_truth(golden_dir)
        categories = load_ws1_config(config_path).taxonomy.categories
        records = _latest_per_record(registry)
        report = evaluate(records, truth, categories)
        # Calibration status breakdown (§3.3): how many rows are calibrated/provisional/etc.
        calibration: dict[str, int] = {}
        for record in records:
            status = record.get("calibration_status") or "unknown"
            calibration[status] = calibration.get(status, 0) + 1
        report["calibration"] = calibration
        return report

    def _rewarm() -> None:
        # A recogniser change alters the detection engine — drop the warm context and
        # rebuild it off the request path so the next run uses the new recognisers.
        service.invalidate()
        threading.Thread(target=service.warm, daemon=True).start()

    @app.get("/api/admin/recognizers")
    def list_recognizers() -> dict[str, Any]:
        """User-managed custom recognisers (merged on top of config + Presidio defaults)."""
        return {"recognizers": [r.model_dump() for r in load_recognizers()]}

    @app.post("/api/admin/recognizers")
    def add_recognizer(rec: StoredRecognizer) -> Response:
        categories = load_ws1_config(config_path).taxonomy.categories
        if rec.category not in categories:
            return JSONResponse(
                {"error": f"category must be one of {categories}"}, status_code=400
            )
        items = load_recognizers()
        if any(r.name == rec.name for r in items):
            return JSONResponse(
                {"error": f"a recognizer named '{rec.name}' already exists"}, status_code=400
            )
        items.append(rec)
        save_recognizers(items)
        _rewarm()
        return JSONResponse({"recognizers": [r.model_dump() for r in items]})

    @app.delete("/api/admin/recognizers/{name}")
    def delete_recognizer(name: str) -> dict[str, Any]:
        items = [r for r in load_recognizers() if r.name != name]
        save_recognizers(items)
        _rewarm()
        return {"recognizers": [r.model_dump() for r in items]}

    @app.get("/api/admin/records/export")
    def admin_records_export(fmt: str = "xlsx") -> Response:
        """Download the processed records as the §3.4 ws1_item_summary in xlsx/csv/jsonl."""
        records = _records_with_reviews()
        name = "ws1_item_summary"
        if fmt == "jsonl":
            body = "".join(
                json.dumps({c: r.get(c) for c in _EXPORT_COLUMNS}) + "\n" for r in records
            )
            return Response(
                body, media_type="application/x-ndjson",
                headers={"Content-Disposition": f'attachment; filename="{name}.jsonl"'},
            )
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(_EXPORT_COLUMNS)
            for r in records:
                writer.writerow([_export_cell(r, c) for c in _EXPORT_COLUMNS])
            return Response(
                buf.getvalue(), media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
            )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "ws1_item_summary"
        sheet.append(_EXPORT_COLUMNS)
        for r in records:
            sheet.append([_export_cell(r, c) for c in _EXPORT_COLUMNS])
        out = io.BytesIO()
        workbook.save(out)
        return Response(
            out.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
        )

    @app.get("/api/admin/stream")
    def admin_stream(request: Request, max_events: int | None = None) -> StreamingResponse:
        async def gen() -> AsyncIterator[str]:
            emitted = 0
            while max_events is None or emitted < max_events:
                if await request.is_disconnected():
                    return
                summary = registry.migration_summary(_authorised()).model_dump()
                jobs = [j.model_dump(mode="json") for j in registry.list(limit=50)]
                yield _sse({"event": "summary", "summary": summary, "jobs": jobs})
                emitted += 1
                if max_events is not None and emitted >= max_events:
                    return
                await asyncio.sleep(1.5)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def __getattr__(name: str) -> Any:
    """Lazily build the ASGI app on first access (uvicorn `app.main:app`).

    Kept out of module import so that merely importing this module (e.g. `from app.main
    import create_app` in tests) does not open the real registry DB or construct a worker
    as an import side-effect. `app` is materialised only when actually referenced.
    """
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
