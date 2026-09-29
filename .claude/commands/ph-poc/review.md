---
name: project:review
description: '3. Multi-agent code review of the current changes'
argument-hint: '[optional: PR number, branch, or file paths]'
---

# /project:review

> **TASK TRACKING:** Create a task for each numbered step. Not done until a
> verdict and prioritized findings are presented.

Review the current changes (default: `git diff` vs the base branch; or the target
in `$ARGUMENTS`).

## Step 1: Determine Scope

Compute the changed files. Detect which areas are affected (WS1 sensitive-data, WS2
matching, shared `libs/`). Read the related plan in `docs/plans/` if one exists.

## Step 2: Spawn Review Agents in Parallel

Launch these agents concurrently with the Agent tool (do not wait for one to finish
before starting the next). Include an agent only if its area changed:

- `learnings-researcher` — relevant past solutions and gotchas.
- `code-quality-reviewer` — YAGNI, duplication, naming, readability, PoC scope.
- `privacy-sentinel` — sensitive content in logs/outputs, minimisation, inference egress, secrets, source immutability.
- `architecture-reviewer` — contracts, reproducibility (manifest/config/ledger), library boundaries.
- `explainability-reviewer` — every output row traceable + reasoned + correctly scored/calibrated.
- `unit-test-reviewer` — coverage gaps on changed lines.

## Step 3: Collect & Classify

Merge findings. Deduplicate. Classify each as **P1 / P2 / P3** per
`.claude/rules/code-review-checklist.md`. Drop anything not backed by evidence
(file:line).

## Step 4: Verdict & Decision Menu

Emit one verdict — `APPROVED`, `APPROVED_WITH_COMMENTS`, or `CHANGES_REQUIRED` —
followed by findings (P1 first). Then present a menu:
1. Auto-fix P1 findings  2. Show P2/P3 detail  3. Create a PR  4. Stop.
