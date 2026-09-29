---
name: project:plan
description: '1. Research prior learnings and produce an implementation plan'
argument-hint: '<feature or bug description>'
---

# /project:plan

> **TASK TRACKING:** Create a task for each numbered step below. Mark each
> complete as you go. This command is NOT done until a plan file is written and
> the user has approved it.

Produce a concrete, reviewable implementation plan for: **$ARGUMENTS**

## Step 1: Restate & Intake

Restate the request in the INTAKE SUMMARY shape from `AGENTS.md` (Goal, Workstream,
Inputs, Sensitivity, Method, Output, Governance, Constraints). If any field is
UNCLEAR, ask the user one question at a time with a recommended default — do not guess
on scope. Confirm the work is in **PoC scope**.

## Step 2: Research Prior Learnings (do NOT skip)

- Search `docs/solutions/` and `docs/solutions/INDEX.md` for related past work.
- Read `.claude/rules/critical-patterns.md` for relevant incident patterns.
- Read the relevant `CLAUDE.md` (root + affected `pipelines/*/CLAUDE.md`) and the
  relevant part of `docs/requirement/`.
- Optionally spawn the `learnings-researcher` agent for a broad sweep.

Report what you found and how it constrains the approach.

## Step 3: Design the Approach

Propose the approach (or 2–3 options with trade-offs for non-trivial work). Check it
against the System Contracts in `CLAUDE.md` — read-only source, sensitive-data
minimisation, controlled inference, explainable + scored output, reproducible runs.
Tag each key decision with a confidence level (CERTAIN / PROBABLE / UNCLEAR).

**Sourcing (mandatory):** per `.claude/rules/citations.md`, web-search each novel
design decision and attach a real citation, or state verbatim **"No source found —
this is an AI-generated idea."** Never fabricate a source. Record the sources in the
plan's "Prior Learnings" section.

## Step 4: Write the Plan

Write the plan to `docs/plans/YYYY-MM-DD-<slug>-plan.md` using
`docs/plans/_template.md`. Include exact file paths, function/type names, config keys
and thresholds touched, the task dependency graph (what can run in parallel), and
test cases (synthetic fixtures).

## Step 5: Decision Gate

Present the plan summary and ask the user to approve, adjust, or reject. Do NOT start
implementation until the plan is approved. Offer to run `/project:implement`.
