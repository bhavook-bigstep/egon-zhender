---
name: compound-docs
description: Capture a solved, verified problem as a categorized solution document in docs/solutions/ so it never has to be re-investigated.
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash
preconditions:
  - The problem has been solved (not in-progress)
  - The solution has been verified working
---

# compound-docs Skill

**Purpose:** Turn a solved, non-trivial problem into durable institutional
knowledge: a categorized doc in `docs/solutions/` plus an updated index, and —
when warranted — a promoted critical pattern.

## Overview

Invoked by `/project:compound`. It captures the *investigation path*, not just
the final fix, so the next person (or agent) understands how the problem was
diagnosed.

## Process

### Step 1: Precondition Check
Confirm the problem is solved and verified. If not, stop.

### Step 2: Choose a Category
One of: `bugs` · `patterns` · `integrations` · `performance` · `security` · `matching`.
(These map to subfolders under `docs/solutions/`. Use `matching` for WS2 linkage/scoring
and `patterns` for cross-cutting method learnings.)

### Step 3: Gather Content
Collect: the symptom, how it was diagnosed (the path), the root cause, the fix,
the key files touched (`path` — why), and how to prevent recurrence.

### Step 4: Validate Frontmatter — [BLOCKING GATE]
Validate the doc's YAML frontmatter against `references/yaml-schema.md`.
**Do NOT proceed past this step if the frontmatter is invalid.**

### Step 5: Write the Document
Write to `docs/solutions/<category>/<slug>.md` using `assets/solution-template.md`.
**Redact all PII** — never paste sensitive content, evidence-span text, OCR text,
or real identifiers into a doc. Reference items by source ID / evidence location only.

### Step 6: Update the Index
Add a one-line entry to `docs/solutions/INDEX.md` under the category.

### Step 7: Promote Patterns
If the root cause is a recurring code/process pattern or a repeat incident, add/strengthen
an entry in `.claude/rules/critical-patterns.md`.

## Success Criteria

- A valid doc exists at `docs/solutions/<category>/<slug>.md`.
- `docs/solutions/INDEX.md` links to it.
- No PII appears anywhere in the doc.
- If recurring, a critical pattern was added/updated.

## Error Handling

- Duplicate found → update the existing doc instead of creating a new one.
- Conflict with existing knowledge → surface it to the user; do not silently overwrite.
