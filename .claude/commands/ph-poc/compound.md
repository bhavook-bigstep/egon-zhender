---
name: project:compound
description: '4. Capture a solved problem as reusable documentation'
argument-hint: '[optional: short description of what was solved]'
---

# /project:compound

> **TASK TRACKING:** Create a task per numbered step. Not done until a solution
> doc is written and the index is updated (or a duplicate is confirmed).

Capture the learnings from the work just completed ($ARGUMENTS) so it never has
to be re-investigated. Only run this for **non-trivial** work.

## Step 1: Precondition Check

Confirm the problem is actually solved and verified. If it is still in progress,
stop and say so.

## Step 2: Duplicate Check

Search `docs/solutions/` and `docs/solutions/INDEX.md` for an existing doc on this
topic. If one exists, update it instead of writing a new one. Flag any conflict
with existing knowledge.

## Step 3: Invoke the compound-docs Skill

Use the `compound-docs` skill to gather context (problem, root cause, solution,
key files, prevention), classify the category, and validate frontmatter.

## Step 4: Write & Index

Write to `docs/solutions/<category>/<slug>.md` using the skill's template. Include
the **investigation path**, not just the final fix. Redact any PII — never paste
sensitive content, evidence text, or real identifiers into a doc. Update
`docs/solutions/INDEX.md`.

## Step 5: Pattern Promotion

If this root cause is a recurring code/process pattern (or a repeat of a prior
incident), add or strengthen an entry in `.claude/rules/critical-patterns.md`.
