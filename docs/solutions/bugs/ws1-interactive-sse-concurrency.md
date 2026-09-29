---
title: Interactive SSE path — deterministic-id PK collision and worker-thread hang
category: bugs
severity: high
date: 2026-09-29
tags: [ws1, sse, concurrency, registry, worker-thread]
related: [docs/solutions/patterns/ws1-web-ui-sse-sqlite-queue.md]
pr: ""
---

# Interactive SSE path — deterministic-id PK collision and worker-thread hang

## Problem

Two defects in the interactive single-job SSE path (`JobService.run_interactive`), both found
in review, both breaking a *normal* operator action (running the live "watch it work" view):

1. **Duplicate primary key on re-run.** Re-running the same `source_id` in the live view threw
   `sqlite3.IntegrityError`, which propagated and broke the SSE stream.
2. **Unbounded hang + stranded job.** If the background work raised, the SSE generator blocked
   forever and the job was left stuck in `RUNNING`.

## Investigation Path

- Defect 1: `run_interactive` created the registry row with `job_id = f"{job_type}-{run_id}"`,
  and `run_id` is deterministic over `{source_id + config_version + seed}`. So a re-run of the
  same item produced the *identical* `job_id` → a second `INSERT` on the `job_id` PRIMARY KEY.
  Unlike `submit`/`run_now` (which use `job-{uuid}`), the interactive path had no uniqueness
  guard. Confirmed by tracing `registry.create` (plain `INSERT`) from the SSE endpoint.
- Defect 2: the worker closure did `box["result"] = run_single(...)` then `events.put(sentinel)`
  — the sentinel was enqueued *only after* a successful return. `run_single` returns a `_failed`
  JobResult for validation errors but can still **raise** (engine init, disk write). On a raise,
  `box["result"]` is never set and the sentinel never enqueued, so the consumer blocks on
  `events.get()` (no timeout) and the job created before the thread started stays `RUNNING`.
  There was no `try/finally`.

## Root Cause

- **Reusing a reproducibility key as a storage primary key.** `run_id` is meant to identify a
  *deterministic run*; making it also the unique registry key means "run the same thing again"
  becomes a key conflict instead of an idempotent replace.
- **A producer thread that signals completion only on the happy path.** Any exception between
  "start" and "enqueue sentinel" deadlocks the consumer and orphans the job state.

## Solution

- Added `JobRegistry.upsert` (`INSERT ... ON CONFLICT(job_id) DO UPDATE`). `run_interactive`
  uses it, keeping the deterministic, stable `job_id` (so the workbook URL is stable) while a
  re-run *replaces* the prior row. Safe because a re-run is idempotent (same `run_id`,
  namespaced output).
- Wrapped the worker body in `try/except/finally`: the sentinel is **always** enqueued in
  `finally`; on exception the error is stored, the consumer emits an `error` SSE frame, and the
  registry job is marked `FAILED` — fail-loud, never hang.

## Key Files

- `libs/registry.py` — new `upsert` (idempotent insert-or-replace for deterministic ids).
- `pipelines/workstream1_sensitive/job_service.py` — `run_interactive` uses `upsert`; worker
  closure has `try/except/finally` + error-frame + FAILED on raise.
- `tests/ws1/test_registry.py` — `upsert` insert/replace (no PK error).
- `tests/ws1/test_job_service.py` — re-run same source doesn't crash (one upserted row);
  worker-error yields an `error` frame and marks the job FAILED (monkeypatched raise).

## Prevention

- A deterministic run key (`run_id`) may identify a run, but the durable-store **primary key**
  for a re-runnable action must be either unique-per-attempt or upserted. Never `INSERT` a
  deterministic id without a conflict clause.
- Any producer/consumer thread that signals via a sentinel/queue must enqueue the sentinel in
  a `finally` so an exception can't deadlock the consumer; surface the error, don't swallow it.

> No PII in this doc — the failing input is referenced as a synthetic source ID shape only.
