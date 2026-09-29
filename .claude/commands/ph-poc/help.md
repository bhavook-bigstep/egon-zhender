---
name: project:help
description: '9. List the project commands and the compound loop'
---

# /project:help

Prince Houston Data Cleansing — **POC** (RFP `EZ-PH-DC-2026-01`). This project uses
the compound engineering loop:
**BRAINSTORM → PLAN → IMPLEMENT → REVIEW → COMPOUND** (see `AGENTS.md`).

Every new idea, fix, or suggestion must be web-searched and either cited or
explicitly labeled AI-generated — see `.claude/rules/citations.md`.

## Commands

| Command               | Purpose                                                    |
| --------------------- | ---------------------------------------------------------- |
| `/project:brainstorm` | Explore a problem space; propose cited approaches          |
| `/project:plan`       | Research prior learnings and write an implementation plan  |
| `/project:implement`  | Execute an approved plan with tests + quality gates        |
| `/project:review`     | Multi-agent code review with a verdict                     |
| `/project:compound`   | Capture a solved problem into `docs/solutions/`            |
| `/project:create-pr`  | Create a structured PR (after explicit approval)           |
| `/project:help`       | Show this reference                                        |

## System Contracts (see `CLAUDE.md`)

1. Source data is **read-only** — never modify a Prince Houston / Zendai record.
2. Sensitive content is PII — minimise it; no external inference without written approval.
3. Every flag and match is **explainable and auditable** (reason + evidence + score type).
4. Runs are **governed and reproducible** (frozen manifest + versioned config + run ledger).
5. **PoC discipline** — fixed scope on the controlled sample; no production over-building.

## Key Locations

- Architecture & contracts: `CLAUDE.md`, `pipelines/*/CLAUDE.md`
- Workflow & roles: `AGENTS.md`
- Enforcement rules: `.claude/rules/`
- Specialist agents: `.claude/agents/`
- Reusable skills: `.claude/skills/`
- Institutional memory: `docs/solutions/` (start at `INDEX.md`)
- Plans: `docs/plans/` · Brainstorms: `docs/brainstorms/`
- Source RFP & response: `docs/requirement/`
