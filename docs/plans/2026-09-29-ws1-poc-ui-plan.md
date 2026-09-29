# Plan: WS-1 PoC UI — operator flow + admin panel (one-process, SQLite queue)

- **Date:** 2026-09-29
- **Author:** Claude
- **Status:** implemented (2026-09-29) — W1–W3 backend + W4 UI + W5 tests/docs landed

## Intake Summary

```
Goal:        A single-process, pure-Python web app (FastAPI) for the PoC that BOTH lets an
             operator run WS-1 (browse source → select → single/batch → live view /
             notifications → workbook results) AND gives an admin panel to monitor the
             whole migration. API/CLI-first; UI is a client; headless runs are recorded too.
Workstream:  Cross-cutting service/registry/worker/UI over WS-1 (WS-2 = placeholder tile).
Inputs:      Frozen manifest + Ws1Config; JobResult/ledger; SQLite registry (= durable queue).
Sensitivity: New access surface — source browsing is metadata-only; no content/evidence
             text in any response, log, registry row, or queue payload; in-boundary/local.
Method:      FastAPI over run_single/run_batch/process_item; SQLite doubles as durable job
             queue (WAL, atomic claim) drained by a worker thread; single = interactive SSE
             run; batch = queued + notifications; HTMX/Jinja + SSE frontend.
Output:      Durable job records + migration reconciliation + operator result views + admin.
Governance:  Selection FREEZES a job manifest + pins config_version; registry = shared
             source of truth (headless + UI); admin surfaces §3.5 reconciliation; controls
             audited; approval-gate surfaced for managed inference.
Constraints: read-only; metadata-only browse; egress gate unchanged; reproducible +
             idempotent; PoC time-box; local (no auth); NO Redis/Celery/Postgres.
```

**PoC scope:** yes — a **synthetic-data demonstration + monitoring** layer, one process,
no extra infra. **Out of PoC scope (named):** auth/SSO/RBAC/audit-at-scale; real Databricks
source browsing of live PII; Redis/Celery/Postgres; §3.4 Delta/Parquet/Excel export; WS-2
flow (placeholder tile only); "view source at evidence location" (gated content view).

## Prior Learnings

- `docs/solutions/INDEX.md` — no prior UI work. `security/inference-egress-minimisation.md`
  + contracts constrain this (metadata-only, egress gate stays in `assess`).
- Critical patterns: #1 read-only (never write source), #2 no content in logs/responses
  (metadata-only everywhere), #3 egress (unchanged).
- Response §3.2/§3.3/§3.4 (row schema, score types, outputs) → the workbook view; §3.5
  (reconciliation) → the admin panel; §5.5 (we provide monitoring dashboards) → admin.
- **Sources:**
  - Server-Sent Events — FastAPI — https://fastapi.tiangolo.com/tutorial/server-sent-events/
    (accessed 2026-09-29): live single-job step stream + admin updates over one HTTP conn.
  - SQLite background job queue (WAL, atomic row claim) — Jason Gorman —
    https://jasongorman.uk/writing/sqlite-background-job-system/ (accessed 2026-09-29):
    durable queue without Redis; "one writer claims rows atomically".
  - FastAPI BackgroundTasks — https://fastapi.tiangolo.com/tutorial/background-tasks/
    (accessed 2026-09-29): in-process, no retry/tracking — hence SQLite-queue + worker for
    the batch path instead.
  - HTMX — https://htmx.org/docs/ (accessed 2026-09-29): SSE + polling via HTML attributes,
    ~14 KB, no build step; vendored locally (no CDN — in-boundary, security.md).
  - Jinja2 (server-rendered templates) + vendored HTMX; single-interactive-vs-queued-batch;
    selection→frozen-job-manifest: **No source found — these are AI-generated design
    choices** (standard patterns; the novel infra bits are cited above).

## Approach

**One FastAPI process, API-first.** `JobService` is the single entry (CLI + API). The
**SQLite registry doubles as a durable job queue**: `submit` inserts a `QUEUED` row; a
**worker thread** claims rows atomically (WAL) and runs `run_batch`, updating progress;
clients poll `/jobs/{id}` or watch SSE; the admin page reads the registry. **Single jobs run
interactively** via an SSE endpoint that executes `process_item` inline and streams each
stage event + finding as it happens (the "watch it work" view). The frontend is **Jinja
server-rendered pages + vendored HTMX + SSE** (minimal JS).

Key decisions (confidence):
- **SQLite = registry + durable queue** (CERTAIN) — WAL + `busy_timeout`; `claim_next()` via
  atomic `UPDATE ... WHERE status='QUEUED' ... RETURNING`. `QueueBackend` seam → Celery/Redis
  in production. Pollable, survives restart (idempotent `run_id`+`resume` make redelivery safe).
- **Single = interactive SSE run; batch = queued + worker** (CERTAIN) — matches "single shows
  live steps; batch runs in background with notifications." Mode is an **explicit choice**, not
  inferred from count.
- **Selection freezes a job manifest + pins `config_version`** (CERTAIN) — the operator selects
  authorised `source_id`s (metadata-only browser); submit snapshots them → governed, reproducible.
- **Frontend = Jinja + vendored HTMX + SSE** (PROBABLE) — server-driven, tiny JS, no build,
  in-boundary (no CDN). Pages: hero, ws1 browser/submit, single-live, results workbook, admin.
- **Approval-gate surfaced** (CERTAIN) — if the selected config uses a managed LLM
  (`is_local=false`), the submit screen shows the written-approval requirement; the pipeline
  gate + config validator still enforce it.

**Contract check:** read-only (source browser is metadata-only; no writes) ✓ · minimisation
(no content/evidence text in responses/registry/queue; findings by location; results show
categories/score_type/band, not matched strings) ✓ · controlled inference (unchanged; approval
surfaced) ✓ · explainable/scored (workbook shows reason + evidence location + score type/band +
calibration; deterministic vs AI distinct) ✓ · reproducible (run_id + config in registry) ✓ ·
local/no-auth (documented).

## Tasks

| # | Task | Files | Depends on | Wave |
| - | ---- | ----- | ---------- | ---- |
| 1 | Extend `Job` (states QUEUED/RUNNING/RETRYING/CANCELLED, progress, run_id, updated_at) + `MigrationSummary` | `libs/jobs.py` | — | 1 |
| 2 | `JobRegistry` (SQLite, WAL) = durable store **+ queue**: create/claim_next/update/get/list/migration_summary | `libs/registry.py` | 1 | 1 |
| 3 | Deps: fastapi, uvicorn[standard], jinja2; vendor `htmx.min.js` | `requirements.txt`, `app/static/vendor/htmx.min.js` | — | 1 |
| 4 | Callbacks on the core: `on_event(stage)` + `on_progress(source_id,status)` + `should_cancel()` (default None) | `pipelines/workstream1_sensitive/{runner,job_runner}.py` | — | 2 |
| 5 | `JobService`: `submit` (enqueue), `run_interactive` (inline generator for SSE), `cancel`, `retry_failed`; records to registry | `pipelines/workstream1_sensitive/job_service.py` | 2,4 | 2 |
| 6 | Worker thread: claim_next → run_batch(on_progress, should_cancel) → update; started on app startup | `pipelines/workstream1_sensitive/worker.py` | 5 | 2 |
| 7 | FastAPI app + API: source (metadata-only, paginated/filter), jobs (submit/get/cancel/retry-failed), single SSE (`/jobs/{id}/stream`), admin summary + `/admin/stream` (SSE), health | `app/main.py`, `app/api.py` | 5,6 | 3 |
| 8 | Wire CLI through `JobService` (headless runs register) | `pipelines/workstream1_sensitive/__main__.py` | 5 | 3 |
| 9 | Frontend — hero (WS-1 / WS-2 placeholder); ws1 browser + select + submit (interactive|batch) + toast/notifications; single **live view** (SSE stage timeline + findings); **workbook results** (filters/pivots, drill to findings + evidence location, reconciliation banner, provenance); **admin panel** (migration tiles, jobs table, exceptions, cancel/retry) | `app/templates/*.html`, `app/static/*` | 7 | 4 |
| 10 | Tests (registry+queue claim, worker, service interactive/submit/cancel/retry, API via TestClient, metadata-only, no-content-leak, SSE smoke, page renders) | `tests/app/*`, `tests/ws1/*` | 5,6,7 | 5 |
| 11 | Docs: WS-1 CLAUDE.md + run note (`uvicorn app.main:app`), redaction note; mark prior API plan superseded | `pipelines/workstream1_sensitive/CLAUDE.md`, `README.md`, `docs/plans/2026-09-29-ws1-api-registry-admin-plan.md` | 7 | 5 |

Waves: **W1**={1,2,3}; **W2**={4,5,6}; **W3**={7,8}; **W4**={9}; **W5**={10,11}.

## Tests

Synthetic + hermetic (TestClient; worker invoked directly/eagerly; no real browser/PII).

- [ ] `test_registry_queue` — enqueue → `claim_next` atomically moves QUEUED→RUNNING; concurrent claim yields each row once; durability on reopen; `migration_summary` aggregates.
- [ ] `test_service_interactive` — `run_interactive("note_001")` yields stage events (extract→…→score) then a final row; reconciles.
- [ ] `test_service_submit_batch` — enqueues; worker drains; registry → COMPLETED + counts; progress advanced.
- [ ] `test_service_cancel` / `test_retry_failed` — cooperative cancel → CANCELLED/partial; retry re-runs only failed ids (resume-style).
- [ ] `test_cli_registers_run` — a headless CLI run appears in the registry.
- [ ] `test_api_source_metadata_only` + `test_api_no_content_leak` — browser/results/stream carry ids + counts + evidence **location** only; never document text or raw identifiers.
- [ ] `test_api_submit_and_results` — POST /jobs (batch) → job_id; results endpoint returns rows; /admin/summary reconciliation.
- [ ] `test_sse_single_stream` + `test_sse_admin_stream` — each yields ≥1 `data:` event.
- [ ] `test_pages_render` — hero, ws1, results, admin return 200 + expected anchors.

## Risks & Rollback

- **Biggest for the time-box:** the operator UI is the largest piece — land wave-by-wave; the
  backend (W1–W3) is independently useful (API/CLI) even if the frontend slips.
- **SQLite write-serialization** → fine at PoC volume; Redis only at sustained high concurrency.
- **In-process worker durability** → QUEUED rows survive restart; in-flight relies on idempotent
  `run_id`+`resume`; document "stale RUNNING" recovery.
- **New PII surface** → strictly metadata-only; no content view in PoC (gated source-view deferred).
- **No auth** → bind `127.0.0.1`; prod SSO/RBAC out of scope.
- **Rollback:** all additive (`libs/registry.py`, `app/`, `worker.py`, `job_service.py`,
  callbacks default None); delete `app/` + worker to revert to CLI/API. No source data touched.

## Review Notes

_(filled in after implementation / review)_
