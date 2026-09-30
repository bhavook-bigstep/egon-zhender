---
title: Eval scorer collapsed three-valued FlagStatus to a boolean, scoring processing failures as correct negatives
category: patterns
severity: high
date: 2026-09-30
tags: [evaluation, scoring, metrics, explainability, unable-to-process]
related: []
pr: ""
---

# Eval scorer collapsed three-valued FlagStatus to a boolean, scoring processing failures as correct negatives

## Problem
The WS-1 expected-vs-actual evaluation (`/admin/eval`, added in the Databricks-source +
eval phase) inflated its headline flagging precision/recall and **hid failed records from
the reviewer**. `FlagStatus` is three-valued (`flagged / not_flagged / unable_to_process`,
`libs/schemas.py`), but the scorer reduced it to a boolean:

```python
actual_flagged = actual_flag == "flagged"   # libs/eval/metrics.py
```

A record whose pipeline outcome was `unable_to_process` (an extraction/OCR/detection
*exception*, not a content judgement) with expected `not_flagged` therefore computed
`expected_flagged=False, actual_flagged=False` → counted as a **true negative**, and its
per-record row got `flag_match = (expected_flagged == actual_flagged)` → **`True`** (a green
✓). The admin "mismatches only" filter (`rows.filter(r => !r.flag_match || !r.categories_match)`)
then hid those records entirely. A processing failure was being reported as a validated
determination — a Contract 3 / `matching-scoring.md` #4 ("no fabricated confidence") violation.

Caught in review (`/ph-poc:review`, explainability-reviewer) before merge — a near-miss, not
a shipped incident. All quality gates were green at the time, because no test exercised the
`unable_to_process` path even though `testing.md` names it a required WS-1 risk path.

## Investigation Path
1. Review agents ran over the eval diff. Five found config/coverage/perf issues; the
   explainability reviewer traced the flag confusion-matrix branch.
2. Read `libs/eval/metrics.py` flag-classification block against `FlagStatus` in
   `libs/schemas.py`: confirmed only `== "flagged"` was tested, so both `not_flagged` and
   `unable_to_process` fell into the same "not flagged" bucket.
3. Followed the value downstream: the `else` branch incremented `tn`, and `flag_match` used
   equality of the two booleans → `True` for an unprocessed record.
4. Followed it to the UI (`app/static/app.js` `renderEvalRows` + the mismatch filter):
   confirmed a `True` flag_match renders ✓ and is filtered *out* of the mismatch view — so
   the reviewer never sees the failure. Root cause confirmed end to end.

## Root Cause
A three-valued status was collapsed to a binary at the scoring boundary. The missing third
state (`unable_to_process`) silently aliased onto "not flagged", so a **processing outcome**
(coverage/reliability) was conflated with a **content determination** (accuracy). Accuracy
metrics must be computed only over records that actually produced a determination.

## Solution
Excluded `unable_to_process` from every accuracy computation and surfaced it as its own
signal instead:

- `evaluate()` short-circuits an `unable_to_process` result: it is **not** added to the
  flagging confusion matrix, per-category counts, or scanned-recall buckets. It is counted
  separately as `counts.unable_to_process`.
- Its per-record row carries `flag_match=None` / `categories_match=None` (not `True`). The UI
  renders `null` as `—` via a `matchMark()` helper (never a fabricated ✓/✗), and because
  `!null` is truthy the "mismatches only" filter now **surfaces** these rows instead of
  hiding them.
- New test `test_evaluate_excludes_unable_to_process` asserts the failed record is not a true
  negative and that `evaluated`/`unable_to_process` counts split correctly.

(Same change set also removed a hardcoded `_TAXONOMY` literal — the per-category breakdown now
threads `cfg.taxonomy.categories` through `evaluate()` — and made `snapshot_id` backend-aware.)

## Key Files
- `libs/eval/metrics.py` — `evaluate()` now excludes `unable_to_process` from tp/fp/fn/tn,
  per-category, and scan-recall; emits `counts.unable_to_process`; takes `categories` instead
  of a module literal.
- `app/static/app.js` — `matchMark()` renders `null` matches as `—`; category breakdown reads
  `report.categories`.
- `tests/ws1/test_eval.py` — `test_evaluate_excludes_unable_to_process` (+ mismatch and
  zero-denominator asserts).

## Prevention
- **Rule of thumb:** when a scorer reads a status enum, handle every member explicitly —
  never let `== "<one-value>"` alias the rest into one bucket. Separate *reliability*
  (processed / failed) from *accuracy* (correct / incorrect); compute accuracy only over
  records that produced a determination.
- **Test the failure state:** `testing.md` already names `unable_to_process` a required WS-1
  risk path — a scorer/metric over `FlagStatus` (and, later, over WS-2 ratings incl.
  `Multiple`/`No match`) must include a test for the non-determination states.
- Promoted to `.claude/rules/critical-patterns.md` (near-miss caught in review 2026-09-30).
