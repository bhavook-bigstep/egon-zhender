# AGENTS.md — How We Work

This file defines the workflow, roles, and approval gates for Claude Code in this
repository. `CLAUDE.md` explains WHY the system is built the way it is; this file
explains HOW we make changes to it. This is a **POC** engagement — keep scope tight.

## Compound Engineering Loop

Every non-trivial change flows through five phases:

**BRAINSTORM → PLAN → IMPLEMENT → REVIEW → COMPOUND**

- **BRAINSTORM** — Explore the problem space; propose 2–3 approaches with trade-offs, each web-searched and cited. (`/project:brainstorm`)
- **PLAN** — Research `docs/solutions/` + code, then write a plan to `docs/plans/`. (`/project:plan`)
- **IMPLEMENT** — Execute the approved plan; write tests; run lint/typecheck/test. (`/project:implement`)
- **REVIEW** — Multi-agent review against the rules and checklist. (`/project:review`)
- **COMPOUND** — Capture non-trivial learnings to `docs/solutions/`. (`/project:compound`)

Trivial changes (typos, config tweaks) skip straight to IMPLEMENT.

## POC-First Principle

This is a time-boxed proof of concept on a **controlled sample**, not the production
system. Prove the method (accuracy, explainability, calibration) on the sample. Do
not build production scale-out, multi-tenant infra, or features that do not change the
PoC result — flag those as out of PoC scope and defer them (`CLAUDE.md` Contract 5).

## Knowledge-First Principle

Before writing code, **search `docs/solutions/` and read the relevant CLAUDE.md**.
We do not re-solve problems we have already solved. Prior learnings, critical
patterns, and past incidents are load-bearing context — consult them first.

## Sourcing Principle (mandatory)

Every new idea, approach, fix, or non-obvious suggestion must be **web-searched
and sourced**. See `.claude/rules/citations.md` for the full rule. In short:

- Use `WebSearch` / `WebFetch` before proposing a novel or contestable idea
  (e.g. an OCR gate heuristic, a Splink blocking rule, a calibration method).
- Attach a real citation (`Title — publisher — URL (accessed YYYY-MM-DD)`) that
  genuinely supports the idea, and never fabricate one.
- If a genuine search finds nothing relevant, say verbatim:
  **"No source found — this is an AI-generated idea."**
- Claims about THIS repo's own code cite `path:line`, not the web.

## Thinking Protocol

For any non-trivial task, before producing output:

1. **Restate** the task to confirm understanding.
2. **List assumptions** — flag anything uncertain (especially volumes, taxonomy, and Zendai snapshot details still TBD).
3. **Identify risks** — top failure modes: source mutation, PII/sensitive-content leakage, uncontrolled inference egress, unexplained/uncalibrated outputs, non-reproducible runs.
4. **Produce output** — plan, code, or review.

## Confidence Levels

| Level    | Meaning                           | Action                       |
| -------- | --------------------------------- | ---------------------------- |
| CERTAIN  | Confirmed by code or docs         | Proceed                      |
| PROBABLE | Consistent with existing patterns | Proceed, note the assumption |
| UNCLEAR  | Multiple valid approaches         | Ask before proceeding        |

## How Approvals Work (Approval Gates)

- **Plan** — The human approves the plan before implementation starts.
- **PoC → production** — Production work begins only after the PoC result is reviewed and approved.
- **Inference egress** — Sending any data to an external/managed inference provider requires **prior written approval** (`CLAUDE.md` Contract 2).
- **Commit / Push** — Never commit, push, or open a PR until the human explicitly requests it.
- **Destructive / outward-facing actions** (deleting data, deploying, posting externally) — confirm first.

## Natural Language Intake

When a request is vague, restate it in this shape before planning:

```
INTAKE SUMMARY
Goal:        [One sentence]
Workstream:  [WS1 sensitive-data / WS2 matching / shared libs]
Inputs:      [Databricks tables/volumes, formats, PoC sample scope]
Sensitivity: [taxonomy categories touched; PII / financial / health / gov-ID / etc.]
Method:      [deterministic rules / OCR / semantic screen / LLM / Splink]
Output:      [row fields produced; explainability + score/band]
Governance:  [manifest, config version, run ledger, reproducibility]
Constraints: [read-only source, no external inference w/o approval, minimisation, PoC time-box]
```

## Agent System Prompts

### PLANNER
- **Role:** Analyze requirements, research the codebase and prior solutions, produce a plan.
- **Loads:** `CLAUDE.md`, relevant `pipelines/*/CLAUDE.md`, `docs/solutions/`, `docs/adr/`, `docs/requirement/`.
- **Output:** A plan following `docs/plans/_template.md`.
- **Rules:** Search `docs/solutions/` FIRST; tag each decision with a confidence level; keep it within PoC scope.

### WORKER (Implementation)
- **Role:** Execute the approved plan, one task per subagent where tasks are independent.
- **Rules:** Follow the plan (no unplanned features); write tests; each subagent only
  touches files in its assigned task; never mutate source data.

### REVIEWER
- **Role:** Evaluate the implementation against the plan, the rules, and the contracts.
- **Output:** A verdict — `APPROVED`, `APPROVED_WITH_COMMENTS`, or `CHANGES_REQUIRED` — with findings.
- **Checklist:** tests present · source untouched · no sensitive content in logs · inference boundary respected · every output row explainable + scored · run reproducible (manifest/version/ledger).

### COMPOUND
- **Role:** Document the solution for future reuse.
- **Rules:** Only for non-trivial work; include the investigation path, not just the fix;
  write to `docs/solutions/<category>/<slug>.md` and update `docs/solutions/INDEX.md`.

## Workflow Orchestration Principles

1. **Parallelize independent work** — spawn subagents concurrently for tasks that don't depend on each other.
2. **Sequence dependent work** — respect the dependency graph from the plan.
3. **Research before building** — a `learnings-researcher` pass precedes non-trivial implementation.
4. **Verify before claiming done** — run lint/typecheck/test; report real results, including failures.
5. **Bounded retries** — auto-fix lint/test failures up to 2 attempts, then surface them.
6. **Fail loud** — never swallow errors to make a step "pass"; emit a typed exception code.

## Task Management

1. Plan first: write checkable items to `tasks/todo.md`.
2. Verify the plan before implementing.
3. Track progress: mark items complete as you go.
4. Explain changes: give a high-level summary at each step.
5. Document results: add a review section to `tasks/todo.md`.
6. Capture lessons: append corrections to `tasks/lessons.md`.

## Core Principles

- **Simplicity first** — the simplest solution that is correct.
- **PoC-scoped** — prove the method on the sample; defer production scale.
- **Minimal impact** — change only what the task requires; never touch source records.
- **Test everything** — no meaningful code without tests.
- **Ask when unsure** — better to ask than to guess wrong (UNCLEAR → ask).
- **Privacy by default** — sensitive content is PII; minimise and keep it in-boundary.
- **Explainable by default** — every flag/match carries a reason and a score type.
- **Cite or disclaim** — every new idea/fix is web-searched and either cited or
  explicitly labeled AI-generated (see `.claude/rules/citations.md`).

## Pre-Work Checklist

- [ ] Searched `docs/solutions/` for prior learnings.
- [ ] Read the relevant `CLAUDE.md` for the workstream being changed.
- [ ] Checked for existing implementations of similar functionality.
- [ ] Confirmed the work is in PoC scope (not deferred production work).
- [ ] Planned tests (unit + a small hermetic integration on fixtures).

## Project Slash Commands Reference

| Command               | Purpose                                         |
| --------------------- | ----------------------------------------------- |
| `/project:brainstorm` | Explore the problem space; cited approaches     |
| `/project:plan`       | Research + produce an implementation plan       |
| `/project:implement`  | Execute the approved plan with tests + checks   |
| `/project:review`     | Multi-agent code review                         |
| `/project:compound`   | Capture learnings to `docs/solutions/`          |
| `/project:create-pr`  | Structured PR creation (after approval)         |
| `/project:help`       | List available commands                         |
