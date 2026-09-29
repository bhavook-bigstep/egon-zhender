---
name: project:implement
description: '2. Execute an approved plan with tests and quality gates'
argument-hint: '[optional: path to a plan file in docs/plans/]'
---

# /project:implement

> **TASK TRACKING:** Create a task for each plan task and each numbered step
> below. Mark each complete as you go. Not done until checks pass (or failures
> are reported) and a decision menu is shown.

Execute the approved plan. If `$ARGUMENTS` names a plan file, use it; otherwise
use the most recent plan in `docs/plans/`.

## Step 1: Load & Parse the Plan

Read the plan. Build the task list and dependency graph. Verify every file path
the plan references still exists; flag drift before writing code.

## Step 2: Execute Tasks

- Run **independent** tasks as parallel subagents (one task each, touching only
  its own files).
- Run **dependent** tasks in dependency order.
- Follow the plan exactly — no unplanned features, and nothing outside PoC scope (YAGNI).
- Honor the System Contracts: read-only source, no sensitive content in logs, no
  external inference without written approval, every output row explainable + scored,
  runs reproducible (manifest + versioned config + ledger).

## Step 3: Write Tests

Add pytest tests for new logic. Cover exception paths (unreadable/unsupported items),
OCR-gate decisions, recogniser hits/misses, and scoring/threshold/rating logic. Use
**synthetic** fixtures only — never real PII. See `.claude/rules/testing.md`.

## Step 4: Quality Gates (bounded retry)

Run lint (`ruff`), typecheck (`mypy`), and tests (`pytest`) for the affected code.
Auto-fix failures, up to **2 attempts** per gate. If still failing, stop and report
the real output — do not mark the step done.

## Step 5: Plan-Compliance Check

Confirm every item in the plan was implemented. List anything deferred and why
(including anything correctly deferred as production-only, out of PoC scope).

## Step 6: Review & Decision Menu

Offer to run `/project:review`. Then present a numbered menu:
1. Fix review findings  2. Run `/project:compound`  3. Create a PR (`/project:create-pr`)
4. Stop here.

Never commit, push, or open a PR without explicit user approval.
