---
name: project:brainstorm
description: '0. Explore a problem space and propose approaches, each backed by a cited source'
argument-hint: '<problem or idea to explore>'
---

# /project:brainstorm

> **TASK TRACKING:** Create a task for each numbered step. This command is NOT
> done until approaches are presented, each carrying either a citation or an
> explicit "no source found — AI-generated" label, and a recommended next step.

This is the first phase of the compound loop
(**BRAINSTORM → PLAN → IMPLEMENT → REVIEW → COMPOUND**). The goal is divergent
exploration, not a final plan. Keep options within **PoC scope**. Explore: **$ARGUMENTS**

## Step 1: Frame the Problem

Restate the problem in the INTAKE SUMMARY shape from `AGENTS.md` (Goal, Workstream,
Inputs, Sensitivity, Method, Output, Governance, Constraints). Note what is in scope
and what is explicitly out of scope for this exploration (and out of PoC scope).

## Step 2: Research Prior Art (do NOT skip)

Two sources, in order:

1. **Internal** — search `docs/solutions/`, `.claude/rules/critical-patterns.md`,
   `docs/requirement/` (the RFP + our response), and the codebase for anything we
   already know. Optionally spawn the `learnings-researcher` agent.
2. **External** — **you MUST use `WebSearch` / `WebFetch`** to find how others have
   solved this (papers, official docs for Presidio / Splink / Docling / PaddleOCR /
   Tika, RFCs, engineering blogs). This is mandatory, not optional.

## Step 3: Generate 2–4 Approaches

For each approach give: the core idea, why it fits our contracts (read-only source,
sensitive-data minimisation, controlled inference, explainable + scored output,
reproducibility), rough effort, and the main risk. Cover a spread — do not propose
four variations of the same idea.

## Step 4: Cite Every Idea — [BLOCKING GATE]

Follow `.claude/rules/citations.md` exactly. For **every** approach, idea, fix, or
suggestion, attach one of:

- **A citation** — a real, web-searched source: `Title — publisher — URL (accessed YYYY-MM-DD)`,
  plus one line on how it supports the idea. Never fabricate a URL or citation.
- **An explicit disclaimer** — if a genuine web search found nothing relevant,
  say verbatim: **"No source found — this is an AI-generated idea."**

Do NOT present any idea without one of these two tags. Uncited, undisclaimed ideas
are a blocking failure of this command.

## Step 5: Compare & Recommend

Summarize the approaches in a short comparison table (approach · effort · risk ·
source-or-AI-generated). Recommend one and say why, noting PoC-time-box impact.

## Step 6: Decision Gate

Offer to capture the exploration to `docs/brainstorms/YYYY-MM-DD-<slug>.md` and to
proceed with `/project:plan` on the chosen approach. Do not start planning or
implementation until the user picks a direction.
