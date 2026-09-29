# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project

| Property        | Value                                                                    |
| --------------- | ------------------------------------------------------------------------ |
| Project         | Prince Houston Legacy Data Cleansing — **POC** (RFP `EZ-PH-DC-2026-01`)   |
| Client          | Egon Zehnder (acquired Prince Houston; data staged in Databricks)        |
| Stage           | **Proof of Concept** — controlled sample precedes any production run      |
| Workstream 1    | Sensitive-data identification (flag file notes/documents by taxonomy)     |
| Workstream 2    | People-record matching (Prince Houston people ⇄ Zendai snapshot)          |
| Language        | Python 3.11+                                                              |
| WS1 stack       | Native extractors · Apache Tika · Docling · PaddleOCR · Presidio · semantic screen (SBERT) · LLM (Qwen, PoC-validated) · score calibration (Platt/isotonic) |
| WS2 stack       | Deterministic keys + blocking · Splink (Fellegi-Sunter) probabilistic linkage |
| Source of truth | Databricks tables/volumes (read-only)                                     |
| Test Runner     | pytest                                                                    |
| Deployment      | Two options: **A** on-premises (EZ Databricks/GPU) · **B** vendor-hosted (dedicated AWS Frankfurt) |

> Stack rows above are the RFP-response baseline. When a real dependency is fixed
> during the PoC (final LLM, Splink config, OCR thresholds), update this table
> first — it is the top of the loading order and everything else inherits from it.

## Documentation Architecture

| File/Folder                     | Role         | Contains                                     |
| ------------------------------- | ------------ | -------------------------------------------- |
| `CLAUDE.md` (this file)         | Architect    | WHY decisions were made, system contracts    |
| `pipelines/*/CLAUDE.md`         | Architect    | Workstream-specific WHY (method choices)     |
| `AGENTS.md`                     | Orchestrator | How to run the compound loop, approval gates |
| `.claude/rules/*.md`            | Enforcement  | WHAT to do (conditionally loaded rules)      |
| `docs/guides/`                  | Knowledge    | HOW humans operate the pipelines             |
| `docs/solutions/`               | Memory       | Past problems + solutions (institutional KB) |
| `docs/adr/`                     | Governance   | Architecture Decision Records                |
| `docs/requirement/`            | Source        | The RFP and our submitted response           |
| `README.md`                     | Onboarding   | Setup and quick start                        |

**CLAUDE.md tells Claude WHY. Rules tell Claude WHAT. Guides tell humans HOW.**
They never swap roles.

## CLAUDE.md Index

| Area          | CLAUDE.md                                  | Scope                                   |
| ------------- | ------------------------------------------ | --------------------------------------- |
| Root          | `CLAUDE.md`                                | Architecture reasoning, contracts       |
| Workstream 1  | `pipelines/workstream1_sensitive/CLAUDE.md`| Extract/OCR/detect/assess/score         |
| Workstream 2  | `pipelines/workstream2_matching/CLAUDE.md` | Deterministic keys + Splink linkage     |

## Compound Engineering

This repo follows the compound loop: **BRAINSTORM → PLAN → IMPLEMENT → REVIEW → COMPOUND**.
Each unit of work should make the next one easier. Before implementing, search
`docs/solutions/` for prior learnings. After solving a non-trivial problem, run
`/project:compound` to capture it. See `AGENTS.md` for the full workflow.

## Architecture

Two independent, auditable batch pipelines over a **frozen** Databricks snapshot.
Neither pipeline ever mutates a source record; both emit one explainable output
row per input item.

```
Workstream 1 (sensitive-data):
  ingest → extract → OCR gate → detect (rules) → semantic screen → LLM assess → score/band → output row

Workstream 2 (people-matching):
  normalise → deterministic keys → blocking → Splink probabilistic linkage → conflict rules → rated output row
```

```
pipelines/workstream1_sensitive/   WS1: extraction, OCR, Presidio recognisers, LLM assessment, scoring
pipelines/workstream2_matching/    WS2: normalisation, blocking, Splink linkage, conflict rules
libs/                              Shared: row schemas, taxonomy config, scoring/calibration, redaction, run ledger
poc/ (created during PoC)          Sample manifests, truth sets, calibration artefacts
docs/                             Guides, solutions (memory), ADRs, plans, brainstorms, requirement
```

## System Contracts

### Contract 1: Source data is read-only — never modify a Prince Houston or Zendai record
**WHY:** The RFP scope boundary is explicit — the vendor identifies and flags; Egon
Zehnder reviews internally. Redacting, deleting, merging, creating, or overwriting a
record without a written change of scope is a contract breach, not a bug.

- Open Databricks tables/volumes read-only; outputs go to a **separate** result set.
- Preserve every source identifier and item of metadata so each output traces back.
- Never run macros or active content in source documents.

### Contract 2: Sensitive content is PII — minimise it and keep it inside the approved boundary
**WHY:** The corpus contains financial, health, government-ID, and compensation data
about real people. A leak is a privacy incident and a client-trust failure.

- **No data reaches a managed/external inference provider without prior written
  approval.** The baseline runs open-weight models on customer-controlled or
  dedicated infrastructure.
- Hash identifiers (email, phone, LinkedIn) with an Egon-Zehnder-held key **before**
  any hosted transfer (data minimisation).
- Never log, print, or write to a doc: raw sensitive content, evidence-span text,
  OCR text, or un-hashed identifiers. Reference items by source ID only.
- Apply retention/TTL to any staged intermediate artefacts.

### Contract 3: Every flag and match is explainable and auditable
**WHY:** Egon Zehnder must review each result and trace it to source. An output the
reviewer cannot explain is unusable.

- WS1 rows carry: source ID, content type, metadata, flag status
  (`flagged / not_flagged / unable_to_process`), category, reason, evidence
  **location** (not content), score **type** (deterministic vs AI/probabilistic),
  score + band + calibration status where applicable, and a processing exception code.
- WS2 rows carry: source person ID, rating (`Confirmed / High / Possible / Multiple /
  No match`), numeric confidence, candidate Zendai IDs, matched + conflicting
  attributes, and review status.
- Deterministic findings cite the rule ID and evidence location; probabilistic/AI
  findings cite the model/linkage and a calibrated score. No unexplained outputs.

### Contract 4: Runs are governed and reproducible
**WHY:** A POC that cannot be re-run identically cannot be validated or accepted.

- Every run reads a **frozen manifest** of authorised source IDs (with content hashes)
  and a **versioned configuration** (taxonomy, thresholds, model version, Splink model).
- Every run writes a **run ledger** (inputs, config version, counts, exceptions,
  reconciliation) so outputs reconcile back to the manifest.
- Runs are deterministic given the same manifest + config + seed; typed exceptions,
  never silent drops.

### Contract 5: POC discipline — fixed scope, no over-building
**WHY:** This is a time-boxed proof of concept on a controlled sample, not the
production system. Scope creep sinks the timeline (target completion 1 Nov 2026).

- One approved taxonomy, one frozen source corpus, one Zendai snapshot, one tuning
  cycle per workstream — per the response's principal assumptions.
- Build what proves the method on the sample; defer production-scale concerns unless
  they change the PoC result. Flag production-only work as out of PoC scope.

## Anti-Patterns

| # | Anti-Pattern                                        | Why It's Wrong                                     | Correct Approach                                             |
| - | --------------------------------------------------- | -------------------------------------------------- | ----------------------------------------------------------- |
| 1 | Writing back to / mutating a source record          | Breaches the RFP scope boundary                    | Read-only source; emit a separate result set                |
| 2 | Sending data to an external LLM/API without approval | Uncontrolled PII egress                             | Customer-controlled/dedicated inference; approval-gated only |
| 3 | Logging sensitive content, evidence text, or raw IDs | Leaks PII into logs                                 | Log source ID + non-identifying metadata only               |
| 4 | Emitting a flag/match with no reason or score       | Reviewer cannot verify or trace it                 | Every row: reason + evidence location + score type/band     |
| 5 | Non-reproducible run (no manifest / version / ledger)| Cannot be validated or accepted                    | Frozen manifest + versioned config + run ledger             |
| 6 | Hardcoding taxonomy, thresholds, model, or secrets  | Unversioned, un-auditable, leaks credentials       | Config + env; keep taxonomy/thresholds/model version explicit |
| 7 | Building production scale-out during the PoC        | Burns the time-box on unproven scope               | Prove the method on the sample; defer scale to production    |

## Enforcement Rules

Full enforcement lives in `.claude/rules/` (loaded conditionally by area):

| Rule Category   | Rule File                              | Loads When You Touch              |
| --------------- | -------------------------------------- | --------------------------------- |
| Python          | `.claude/rules/python.md`              | `.py` files                       |
| Privacy / PII   | `.claude/rules/privacy-sensitive-data.md` | sensitive content, identifiers, logs |
| Security        | `.claude/rules/security.md`            | secrets, access, inference egress |
| Data pipeline   | `.claude/rules/data-pipeline.md`       | ingest, extract, OCR, ledgers     |
| Matching/scoring| `.claude/rules/matching-scoring.md`    | detection scores, Splink, calibration |
| Testing         | `.claude/rules/testing.md`             | test files / new code             |
| Performance     | `.claude/rules/performance.md`         | batch processing / large corpus   |
| Citations       | `.claude/rules/citations.md`           | any new idea/fix/suggestion (always) |
| Critical        | `.claude/rules/critical-patterns.md`   | always relevant (incidents)       |

## Commands

```bash
# Environment (uv recommended; plain pip works)
uv venv && uv pip install -r requirements.txt   # or: pip install -r requirements.txt

# Tests & quality
pytest                       # tests
ruff check .                 # lint
mypy libs pipelines          # type check

# Regenerate the WS-1 synthetic test fixtures (hermetic; no PII)
python tests/fixtures/build_ws1_sample.py

# Run WS-1 on the sample test env (manifest is named by the config)
python -m pipelines.workstream1_sensitive --config config/ws1.yaml

# WS-2 (not yet scaffolded — placeholder entry point)
python -m pipelines.workstream2_matching  --config config/ws2.yaml
```

> WS-1 is scaffolded (walking skeleton). The `source.manifest` and thresholds live in
> `config/ws1.yaml`; the synthetic sample lives under `tests/fixtures/` (real
> controlled-sample data goes in the git-ignored `poc/`). WS-2 remains a placeholder.

## Important Instruction Reminders

- Do what has been asked; nothing more, nothing less (PoC scope — Contract 5).
- Prefer editing existing files to creating new ones.
- Never modify a source record; never send data to external inference without written approval.
- Never commit, push, or open a PR until the user explicitly approves (see `AGENTS.md`).
- Search `docs/solutions/` before implementing; capture learnings after.
