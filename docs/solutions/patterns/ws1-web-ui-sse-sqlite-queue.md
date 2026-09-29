---
title: One-process web UI — SQLite-as-durable-queue + worker thread + SSE + metadata-only surface
category: patterns
severity: medium
date: 2026-09-29
tags: [ws1, web-ui, sse, sqlite-queue, privacy]
related: [docs/solutions/bugs/ws1-interactive-sse-concurrency.md, docs/solutions/security/inference-egress-minimisation.md]
pr: ""
---

# One-process web UI — SQLite-as-durable-queue + worker thread + SSE + metadata-only surface

## Problem

The PoC needed an operator UI (browse source → run WS-1 → watch it work → results) **and**
an admin migration monitor, usable **without** the UI (API/CLI-first for production), on a
time-box that ruled out Redis/Celery/Postgres. It also opened the first web surface over a
corpus that is entirely sensitive PII — so a naive UI could easily leak content or spawn
uncontrolled infra. No prior UI/SSE/queue pattern existed in the repo.

## Investigation Path

- Rejected Databricks-native jobs/pipelines: the engagement has **two** deployment targets
  (Option A on-prem Databricks, Option B dedicated AWS Frankfurt with no Databricks), so the
  orchestration must be portable — custom runtime, not platform-locked.
- Rejected Redis/Celery/Postgres for the PoC: production seam, not needed to prove the method
  on the sample (Contract 5). Cited SQLite-background-job-queue + FastAPI-SSE sources in the
  plan.
- Chose **one FastAPI process**: `JobService` is the single entry for CLI + API + UI, and the
  **SQLite registry doubles as the durable job queue** (WAL + `busy_timeout`, atomic
  `claim_next`), drained by a **worker thread**. Single jobs run **interactively** over an SSE
  endpoint (`run_single` with an `on_event` hook); batch jobs are **queued** and observed.
- The privacy risk drove a hard rule: every surface is **metadata-only** — findings by
  **evidence location**, never the matched string / OCR text / raw identifiers.

## Root Cause

N/A — this is a green-field pattern capture, not a defect. The learning is the *shape* of a
portable, privacy-safe, infra-light UI+monitor that stays API/CLI-first.

## Solution

- **Durable queue in SQLite:** `JobRegistry` (WAL, `threading.Lock`, atomic `claim_next`
  QUEUED→RUNNING) is the `QueueBackend` seam; production swaps Redis/Celery without changing
  callers. Headless CLI runs record to the same registry, so the admin monitor sees them too.
- **Single = interactive SSE run; batch = queued + worker.** Mode is an explicit operator
  choice, not inferred from count. The live view streams stage events (extract → OCR gate →
  detect → assess → score) content-free.
- **Frontend = server-rendered Jinja + vendored HTMX + native SSE (EventSource).** No CDN
  (in-boundary), no build step. HTMX only for source-browser pagination; EventSource for the
  live + admin streams.
- **Reproducibility carried through:** `run_id = f(sorted selection + config_version + seed)`;
  outputs are namespaced per run (`single-<run_id>/`, `batch-<run_id>/`) and sorted on write.

### Gotchas found (each fixed, each a reuse note)

1. **Import side-effect.** A module-level `app = create_app()` opened the real registry DB
   (and built a Worker) at *import* time, polluting the repo and hurting test hermeticity.
   Fix: PEP 562 `def __getattr__(name)` builds `app` lazily on first access, so `uvicorn
   app.main:app` still works but `import app.main` has no side-effect.
2. **Admin SSE N+1.** The admin stream recomputed the authorised count by re-reading +
   re-parsing the whole frozen manifest every 1.5 s per open tab — fine on the sample, a
   repeated full-corpus read at production volume (`performance.md`). Fix: cache the count
   once per process (the manifest is frozen for the run).
3. **Metadata-only drift.** The pre-processing source browser drops `content_hash` **and**
   `path`; `content_hash` is intentionally kept in *result* rows (post-processing provenance
   / reconciliation) — document the asymmetry so it isn't "fixed" the wrong way.
4. **Concurrency of the interactive path** — see [[ws1-interactive-sse-concurrency]].

## Key Files

- `libs/registry.py` — SQLite WAL durable store + queue; `claim_next`, `upsert`,
  `migration_summary` (per-job counts, `pct_complete` clamped ≤100 for re-run overlap).
- `pipelines/workstream1_sensitive/worker.py` — worker thread; fail-loud, guarded `claim_next`.
- `pipelines/workstream1_sensitive/job_service.py` — single entry (submit/execute/run_now/
  run_interactive); `_apply_result` shared so no path drops `result.exception`.
- `app/main.py` — FastAPI: metadata-only source browse, jobs API, SSE (`/api/interactive/
  stream`, `/api/admin/stream`), server-rendered pages, lazy `__getattr__` app.
- `app/templates/*.html`, `app/static/{app.js,app.css,vendor/htmx.min.js}` — UI.

## Prevention

- Reuse this shape for the WS-2 UI: `JobService` + registry + worker + SSE, metadata-only.
- Any new response/SSE surface: emit source ID + evidence **location** only; escape every
  server-derived value client-side (see the critical-patterns entry on UI/SSE surfaces).
- Keep the app factory side-effect-free; never do I/O or start threads at module import.
- Don't recompute frozen-manifest-derived constants per SSE tick.

> Redact PII: this doc references items by role/shape only; no sensitive content, evidence
> text, OCR text, or real identifiers appear here.
