---
title: <TITLE>
category: <bugs|patterns|integrations|performance|security|matching>
severity: <low|medium|high|critical>
date: <YYYY-MM-DD>
tags: [<tag1>, <tag2>]
related: []
pr: ""
---

# <TITLE>

## Problem
What was observed (the symptom). Where it showed up (`path:line`, pipeline stage,
workstream). Reference items by source ID only — never sensitive content.

## Investigation Path
How it was diagnosed, in order. What was ruled out. This is the most valuable
part — it lets the next person skip the dead ends.

## Root Cause
The actual underlying cause (not just the surface symptom).

## Solution
What was changed to fix it. Include code where it clarifies.

## Key Files
- `path/to/file` — what changed and why.

## Prevention
How to stop this from recurring: a rule, a test, a critical pattern, a config guard.
If a `.claude/rules/critical-patterns.md` entry was added, link it here.

> Redact PII: never include sensitive content, evidence-span text, OCR text, or
> real identifiers (email/phone/LinkedIn). Reference by source ID / evidence location.
