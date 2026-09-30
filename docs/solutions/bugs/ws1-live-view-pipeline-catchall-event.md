---
title: Live step-view animation spun forever on failure — exceptions emit as a "pipeline" catch-all event
category: bugs
severity: medium
date: 2026-09-30
tags: [sse, live-view, pipeline-events, ui, stepper]
related: []
pr: ""
---

# Live step-view animation spun forever on failure — exceptions emit as a "pipeline" catch-all event

## Problem
On the interactive live run view (`/ws1/live`), the step-by-step pipeline is a state machine
driven by SSE `stage` events. When an item **failed** mid-pipeline (e.g. a heavy scanned PDF
that OCR can't read), the **currently-running step kept its spinner/animation going forever** —
it was never marked failed, and the run never visibly ended. User-reported ("even when the
processing fails the pipeline animation keeps going").

## Investigation Path
1. The live view keys off SSE `stage` events, one per completed pipeline stage, in a known
   order: `ingest → extract → ocr_gate → detect → screen → assess → score`. As each arrives it
   settles that step and advances the "running" indicator to the next.
2. Read the run ledger (`stage_events`) for a failing item: the events were
   `ingest (done) → extract (done) → pipeline -> failed (exc: ocr_failure)`. **The failure was
   emitted under stage `"pipeline"` — not under `ocr_gate`, the stage that actually raised.**
3. Confirmed the source: `pipelines/workstream1_sensitive/runner.py:380,402` record a
   `stage="pipeline"` event (with the exception code / `internal_error`) whenever any stage
   raises — a single top-level catch-all, not a completion of the specific stage.
4. In the UI, `pipeline` is not in the known step list, so the handler ignored it: the step that
   was mid-flight (`ocr_gate`) never received a completion event and stayed in the animating
   `running` state. `done`/`error`/disconnect also didn't settle a leftover running step.

## Root Cause
The interactive stage stream reports a mid-pipeline exception as **one catch-all
`stage: "pipeline"` event carrying the exception code**, rather than as a (failed) completion of
the stage that raised. A UI state machine that only handles the enumerated stage names silently
drops that event, so the active step is never terminated and its animation never stops.

## Solution
Handle the catch-all and always settle running state on any terminal signal
(`app/static/app.js`, `initLive`):
- A `stage` event whose name is **not** a known step **but carries `exception_code`** now fails
  the **currently running** step: it stops the animation and marks that step failed with the
  code (`stopRunning(exceptionCode)`).
- A **known** stage that itself carries `exception_code` is marked failed and no next step starts.
- `done`, `error`, and the SSE `onerror` (disconnect) all call `stopRunning()` so nothing is left
  spinning; status reflects the failure ("Stopped — unable to process" / "Failed: <code>").

(Done alongside a live-view redesign — a centered stepper that shows only ran + running steps and
FLIP-recenters as each appears — but the correctness fix is the catch-all handling above.)

## Key Files
- `app/static/app.js` — `initLive`: `stopRunning()` / `setDone()` / the `stage`/`done`/`error`/
  `onerror` handlers; treats an exception-bearing or catch-all event as terminal for the active step.
- `pipelines/workstream1_sensitive/runner.py:380,402` — where a mid-pipeline exception is emitted
  as `stage="pipeline"` (the event a consumer must handle).

## Prevention
- **Any consumer of the interactive stage stream must treat an exception-bearing event as terminal
  for the active step, and settle running state on `done`/`error`/disconnect** — never assume every
  started step will get a matching named-stage completion. Enumerate the emitted stages *including*
  the `pipeline` catch-all.
- Possible pipeline-side follow-up: emit the failure under the specific stage name (with an
  exception code) so consumers don't need the catch-all. Until then, the catch-all is the contract.
- Related UI/SSE learnings: `docs/solutions/patterns/ws1-web-ui-sse-sqlite-queue.md` (the UI shell),
  `docs/solutions/bugs/ws1-interactive-sse-concurrency.md` (a separate SSE concurrency bug).
