# Plan: WS-1 API-first service + durable jobs + run registry + admin monitor

- **Date:** 2026-09-29
- **Author:** Claude
- **Status:** superseded by `2026-09-29-ws1-poc-ui-plan.md` (which folds this API/registry/
  admin scope into the one-process UI + admin build). Kept for history.

## Intake Summary

```
Goal:        API/CLI-first service over the job layer with DURABLE async execution
             (queue + worker), retries, and a pollable, persisted run registry — plus a
             local admin page that monitors the whole migration. UI is a client;
             headless is the production path.
Workstream:  Cross-cutting service/registry/worker over WS-1 (WS-2 later) + admin page.
Inputs:      Frozen manifest + Ws1Config; JobResult/ledger; the run registry (new).
Sensitivity: The API is a NEW access surface — metadata-only, no content in responses/
             logs, in-boundary only.
Method:      JobService enqueues jobs to a durable queue (Celery + Redis); a worker runs
             the existing run_single/run_batch, records to the registry, retries transient
             failures; clients poll the registry (and/or SSE).
Output:      Durable job records + migration-reconciliation summary + admin HTML page.
Governance:  Registry = shared, durable source of truth for headless + UI; every job
             records config_version/run_id/engines; admin surfaces §3.5 reconciliation;
             controls (cancel/retry) are audited API calls.
Constraints: read-only source; metadata-only browsing; approval-gated egress (unchanged);
             reproducible + idempotent (safe retries); PoC time-box; local (no auth) —
             prod auth/SSO/RBAC is out of scope.
```

**PoC scope:** yes — durable async is now in scope, run locally via Docker (Redis +
a worker). **Out of PoC scope (named):** SSO/RBAC/audit hardening; Postgres registry
(SQLite is fine locally); Databricks-Apps hosting; the operator submit-flow UI (next plan).

## Prior Learnings

- `docs/solutions/INDEX.md` — no prior API/UI/registry work. `security/inference-egress-
  minimisation.md` + contracts constrain this (egress gate stays in `assess`).
- Critical patterns: #1 read-only (never write source), #2 no content in logs/responses
  (metadata-only), #3 egress (unchanged; gate already in the pipeline).
- Response §3.5 (internal) — the admin reconciliation IS "authorised = processed +
  excluded; processed = flagged + not flagged + unable" + append-only audit, live.
- Response §5.5 (internal) — we committed to providing "job progress, exceptions,
  throughput and reconciliation dashboards" (this admin page) + our own project runtime
  owning orchestration (custom, not Databricks-native — portable across Option A & B).
- **Sources:**
  - Celery (durable task queue + retries + result backend) — TestDriven.io (FastAPI+Celery)
    — https://testdriven.io/courses/fastapi-celery/intro/ (accessed 2026-09-29): battle-
    tested distributed queue with retries, result backend, and Flower monitoring.
  - ARQ — https://github.com/python-arq/arq (accessed 2026-09-29): async-native Redis queue
    — **rejected: now maintenance-only**, so not a safe base for a durable foundation.
  - Redis — https://redis.io/docs/ (accessed 2026-09-29): broker/result store for the queue.
  - Server-Sent Events — FastAPI — https://fastapi.tiangolo.com/tutorial/server-sent-events/
    (accessed 2026-09-29): live admin updates (polling the registry).
  - sqlite3 — Python docs — https://docs.python.org/3/library/sqlite3.html
    (accessed 2026-09-29): the durable, pollable registry store (Postgres for prod).
  - Idempotent/at-least-once + retries needing idempotency: **No source found — this is an
    AI-generated design point** (our deterministic run_id + resume make retries safe).

## Approach

**API-first, one core, durable queue.** `JobService` is the single entry for CLI (headless)
and API; it **enqueues** a job onto a **durable queue (Celery + Redis)** and records it in
the **persisted registry**. A **worker** process runs the existing `run_single`/`run_batch`
executors, updates the registry with progress, and **retries transient failures**. Clients
learn status by **polling the registry** (`GET /jobs/{id}`) and/or the SSE stream. The admin
page is a pure client of the registry. Nothing is UI-only; nothing lives only in memory.

Key decisions (confidence):
- **Durable queue = Celery + Redis** (CERTAIN) — active, battle-tested, built-in retries +
  result backend; ARQ rejected (maintenance-only). Runs locally via Docker; portable to
  Option A & B (no Databricks lock-in).
- **Pollable store = the run registry (SQLite locally, Postgres in prod)** (CERTAIN) — the
  **authoritative, durable** record of every job (headless + API): status, run_id,
  config_version, counts, engines, timestamps, result paths, progress. Survives restarts.
- **Retry policy** (PROBABLE):
  - **Transient** infra/service failures (queue task raises) → **Celery auto-retry with
    exponential backoff**, bounded `max_retries`.
  - **Deterministic** item errors (`UNSUPPORTED_TYPE`, `HASH_MISMATCH`) → **not** retried →
    `unable_to_process` row (retrying would fail identically).
  - **Item-level transient** (`EXTRACTION_ERROR`/`OCR_FAILURE`/`DETECTION_ERROR` from a
    down service) → row now, but **retryable**: a `POST /jobs/{id}/retry-failed` re-runs
    just those `source_id`s (resume-style).
  - **Safe because idempotent:** deterministic `run_id` + `resume` + one-row-per-input mean
    re-running never double-counts.
- **Job states** (CERTAIN): `PENDING → QUEUED → RUNNING → COMPLETED` · `RETRYING` ·
  `FAILED` (run-level) · `CANCELLED`.
- **Cancel** (PROBABLE) — cooperative flag checked by the worker between items; remaining
  items left unprocessed, what ran still reconciles.
- **SSE by polling the registry** (PROBABLE) — `/admin/stream` emits summary + active jobs
  every ~1.5 s; WebSocket later.

**Contract check:** read-only ✓ · minimisation (no content/evidence text in responses,
registry, or queue payloads — jobs carry source_ids + config only) ✓ · controlled inference
(unchanged) ✓ · explainable/scored (unchanged; admin adds provenance) ✓ · reproducible +
**idempotent retries** (run_id + resume) ✓ · local, no auth (documented).

## Tasks

| # | Task | Files | Depends on | Wave |
| - | ---- | ----- | ---------- | ---- |
| 1 | Extend `Job` (run_id, progress_done/total, updated_at) + add `QUEUED/RETRYING/CANCELLED` + `MigrationSummary` | `libs/jobs.py` | — | 1 |
| 2 | `JobRegistry` (SQLite, durable/pollable): create/update/get/list/migration_summary; WAL + write lock | `libs/registry.py` | 1 | 1 |
| 3 | Deps: celery, redis, fastapi, uvicorn[standard] | `requirements.txt` | — | 1 |
| 4 | `on_progress` + `should_cancel` callbacks on `run_single`/`run_batch` (default None) | `pipelines/workstream1_sensitive/{runner,job_runner}.py` | — | 2 |
| 5 | Celery app + `process_job` task (runs executor, updates registry, retry policy) + worker entrypoint | `pipelines/workstream1_sensitive/tasks.py`, `celery_app.py` | 2,4 | 2 |
| 6 | `JobService`: run_now (sync, CLI) + submit (enqueue, API) + cancel + retry_failed; records to registry | `pipelines/workstream1_sensitive/job_service.py` | 5 | 2 |
| 7 | Redis (+ worker) in compose; local run docs | `docker-compose.yml`, `README.md` | 3 | 2 |
| 8 | FastAPI: /health, POST /jobs, GET /jobs[/{id}] (poll), GET /admin/summary, GET /admin/stream (SSE), POST /jobs/{id}/cancel, POST /jobs/{id}/retry-failed, GET /source/manifest (metadata-only), GET / (admin.html) | `app/main.py` | 6 | 3 |
| 9 | Wire CLI through `JobService` so headless runs register | `pipelines/workstream1_sensitive/__main__.py` | 6 | 3 |
| 10 | Admin monitor page (summary tiles, jobs table w/ progress+provenance+retries, exceptions, cancel/retry; SSE live) | `app/static/admin.html` | 8 | 4 |
| 11 | Tests (registry, service, task retry, API via TestClient, CLI-registers, summary) — worker mocked/eager | `tests/ws1/*`, `tests/app/*` | 6,8,9 | 5 |
| 12 | Docs: WS-1 CLAUDE.md + run note (redis, worker, uvicorn); redaction note | `pipelines/workstream1_sensitive/CLAUDE.md`, `README.md` | 8 | 5 |

Waves: **W1**={1,2,3}; **W2**={4,5,6,7}; **W3**={8,9}; **W4**={10}; **W5**={11,12}.

## Tests

Synthetic + hermetic. Celery runs in **eager mode** (`task_always_eager`) for tests, so no
live broker is needed; a small live smoke is optional (skips if Redis down).

- [ ] `test_registry` — CRUD + `migration_summary` aggregation; durability (reopen DB); WAL.
- [ ] `test_job_service_single` / `_batch_progress` — run_now/submit → registry states + counts + progress.
- [ ] `test_task_retry_transient` — a transient failure triggers Celery retry then succeeds; deterministic item error does **not** retry (→ unable_to_process row).
- [ ] `test_retry_failed_endpoint` — re-runs only the failed source_ids (resume-style); reconciles.
- [ ] `test_job_service_cancel` — cooperative cancel → CANCELLED/partial; what ran reconciles.
- [ ] `test_cli_registers_run` — a headless CLI run appears in the registry.
- [ ] `test_api_submit_poll_summary` — POST /jobs → job_id; GET /jobs/{id} polls to COMPLETED; /admin/summary reconciliation.
- [ ] `test_api_source_metadata_only` + `test_api_no_content_leak` — no content/raw ids in responses, registry, or queue payloads.
- [ ] `test_api_stream_smoke` — /admin/stream yields ≥1 event.

## Risks & Rollback

- **New infra (Redis + worker)** → local via Docker; worker crash → queue redelivers
  (at-least-once); idempotent run_id + resume make redelivery safe (no double count).
- **At-least-once ⇒ possible duplicate execution** → idempotency (run_id + resume + one-row-
  per-input) is the guard; document it.
- **Registry durability** → SQLite WAL + write lock for local single-node; Postgres for prod.
- **Auth deferred** → bind to `127.0.0.1`; prod SSO/RBAC/audit out of scope.
- **Scope** → operator submit-flow UI is the *next* plan; §3.4 Delta/Parquet/Excel export is separate.
- **Rollback:** additive (`libs/registry.py`, `app/`, `tasks.py`, `celery_app.py`, `job_service.py`, compose `redis`); set jobs back to `run_now` (sync) and delete the queue pieces to revert. No source data touched; nothing committed.

## Review Notes

_(filled in after implementation / review)_
