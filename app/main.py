"""FastAPI service for WS-1 (PoC).

API-first: the CLI and this API share `JobService` + the registry. All responses are
METADATA ONLY — never document content or raw identifiers. Local/no-auth (PoC); bind to
loopback. The frontend pages (operator flow + admin) are added in the next wave; this
module is the backend API + SSE.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from libs.config import load_ws1_config
from libs.jobs import Job, JobRequest
from libs.registry import JobRegistry
from libs.schemas import Finding, ScoreType, Ws1Summary
from pipelines.workstream1_sensitive.extract_engine import build_extraction_engine
from pipelines.workstream1_sensitive.ingest import ingest
from pipelines.workstream1_sensitive.job_service import JobService
from pipelines.workstream1_sensitive.runner import build_reader
from pipelines.workstream1_sensitive.worker import Worker

_APP_DIR = Path(__file__).resolve().parent
_PAGE_SIZE = 100
_MATCH_CONTEXT_CHARS = 48


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


def _reveal_matched_content(
    config_path: str, findings_by_source: dict[str, list[dict[str, Any]]]
) -> None:
    """PoC / human-review only: attach the matched span (char_pre/char_match/char_post) to
    each finding that has char offsets, re-derived LIVE from the read-only source.

    Deliberately NOT persisted — nothing is written to the result rows, ledger, registry,
    or logs (Contracts 2 & 3 keep the durable artefacts content-free). Computed at render
    time, in-boundary, and gated by the caller (off by default). The sample is synthetic.
    """
    cfg = load_ws1_config(config_path)
    reader = build_reader(cfg)
    engine = build_extraction_engine(cfg.extract)
    by_id = {e.source_id: e for e in reader.list_manifest()}
    text_cache: dict[str, str | None] = {}

    def _text(source_id: str) -> str | None:
        if source_id not in text_cache:
            entry = by_id.get(source_id)
            try:
                text_cache[source_id] = (
                    engine.extract(entry, ingest(reader, entry)).text
                    if entry is not None
                    else None
                )
            except Exception:  # extraction may fail for this item — just show no snippet
                text_cache[source_id] = None
        return text_cache[source_id]

    for source_id, items in findings_by_source.items():
        for finding in items:
            loc = finding.get("evidence_location") or {}
            start, end = loc.get("char_start"), loc.get("char_end")
            if start is None or end is None:
                continue
            text = _text(source_id)
            if not text or start >= len(text):
                continue
            end = min(end, len(text))
            finding["char_pre"] = text[max(0, start - _MATCH_CONTEXT_CHARS) : start]
            finding["char_match"] = text[start:end]
            finding["char_post"] = text[end : end + _MATCH_CONTEXT_CHARS]


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
    # Off by default (production-safe). Opt-in reveals the matched span in the review UI,
    # re-derived live from the read-only source and never persisted (Contracts 2 & 3).
    if reveal_matches is None:
        reveal_matches = os.environ.get("WS1_SHOW_MATCHED_CONTENT") == "1"

    registry = JobRegistry(registry_db)
    service = JobService(config_path, registry)
    worker = Worker(service, registry) if start_worker else None

    _authorised_cache: dict[str, int] = {}

    def _authorised() -> int:
        # The manifest is frozen for the life of a run, so the authorised count is constant;
        # cache it instead of re-reading + re-parsing the whole manifest on every admin SSE
        # tick (a repeated full-corpus-metadata read at production volume — performance.md).
        if "n" not in _authorised_cache:
            cfg = load_ws1_config(config_path)
            _authorised_cache["n"] = len(build_reader(cfg).list_manifest())
        return _authorised_cache["n"]

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if worker is not None:
            worker.start()
        yield
        if worker is not None:
            worker.stop()
        registry.close()

    app = FastAPI(title="WS-1 PoC service", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(_APP_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(_APP_DIR / "templates"))

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
        cfg = load_ws1_config(config_path)
        entries = build_reader(cfg).list_manifest()
        window = entries[:_PAGE_SIZE]
        next_offset = _PAGE_SIZE if len(entries) > _PAGE_SIZE else None
        return templates.TemplateResponse(
            request=request,
            name="ws1.html",
            context={
                **_config_meta(),
                "items": window,
                "total": len(entries),
                "next_offset": next_offset,
            },
        )

    @app.get("/ws1/rows", response_class=HTMLResponse)
    def page_ws1_rows(request: Request, offset: int = 0) -> Any:
        """HTMX fragment: the next page of source rows (+ an OOB load-more button)."""
        cfg = load_ws1_config(config_path)
        entries = build_reader(cfg).list_manifest()
        window = entries[offset : offset + _PAGE_SIZE]
        nxt = offset + _PAGE_SIZE
        next_offset = nxt if len(entries) > nxt else None
        return templates.TemplateResponse(
            request=request,
            name="_rows.html",
            context={
                "items": window,
                "total": len(entries),
                "next_offset": next_offset,
                "oob": True,
            },
        )

    @app.get("/ws1/live", response_class=HTMLResponse)
    def page_live(request: Request, source_id: str) -> Any:
        return templates.TemplateResponse(
            request=request, name="live.html", context={"source_id": source_id}
        )

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
        if reveal_matches:
            _reveal_matched_content(config_path, findings_by_source)
        return templates.TemplateResponse(
            request=request,
            name="results.html",
            context={
                "job": job,
                "rows": rows,
                "findings_by_source": findings_by_source,
                "reconcile": job.result.reconcile if job.result else None,
            },
        )

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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/source/manifest")
    def source_manifest(offset: int = 0, limit: int = 100) -> dict[str, Any]:
        """Metadata-only view of authorised items (no content)."""
        cfg = load_ws1_config(config_path)
        entries = build_reader(cfg).list_manifest()
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

        def gen() -> Iterator[str]:
            for event in service.run_interactive(request):
                yield _sse(event)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/admin/summary")
    def admin_summary() -> dict[str, Any]:
        return registry.migration_summary(_authorised()).model_dump()

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
