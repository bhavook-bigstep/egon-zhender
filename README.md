# Prince Houston Legacy Data Cleansing — POC

Proof of concept for RFP **`EZ-PH-DC-2026-01`** (Egon Zehnder). Before any import
into Zendai, identify **which Prince Houston file notes and documents contain highly
sensitive information** (Workstream 1) and **which Prince Houston people already exist
in Zendai** (Workstream 2). Outputs are auditable and explainable; every decision, and
every record, stays with Egon Zehnder.

This is a **time-boxed proof of concept on a controlled sample** — it proves the
method (accuracy, explainability, calibration) ahead of a production run. Keep scope
tight (see `CLAUDE.md` Contract 5).

## Structure

```
pipelines/workstream1_sensitive/   WS1: ingest → extract → OCR gate → detect → assess → score → output
pipelines/workstream2_matching/    WS2: normalise → deterministic keys → blocking → Splink → conflict → rating
libs/                             Shared: row schemas, taxonomy config, scoring/calibration, redaction, run ledger
docs/                             Guides, solutions (memory), ADRs, plans, brainstorms, requirement (RFP + response)
.claude/                          Claude Code setup (rules, commands, agents, skills, hooks)
```

## Workstreams

| # | Workstream                  | Scope (approx.)                         | Method                                                                 |
| - | --------------------------- | --------------------------------------- | --------------------------------------------------------------------- |
| 1 | Sensitive-data identification | 330k file notes + 90k documents (~55 GB) | Native/Tika/Docling extraction · gated PaddleOCR · Presidio · semantic + LLM (Qwen, PoC-validated) |
| 2 | People-record matching        | 88k people ⇄ minimised Zendai snapshot   | Deterministic keys + blocking · Splink (Fellegi-Sunter) probabilistic linkage |

## Deployment Options

- **Option A — on-premises:** processed on Egon Zehnder Databricks / GPU hosts (baseline).
- **Option B — vendor-hosted:** dedicated single-tenant AWS account, Frankfurt.

The controls are identical for both; only the boundary moves. No data reaches a
managed/external inference provider without prior written approval.

## Prerequisites

- **Python 3.11+**. `uv` is recommended; plain `pip` works too.
- Read-only access to the approved Databricks tables/volumes (provisioned per the engagement).
- Open-weight model inference on customer-controlled or dedicated infrastructure
  (baseline Qwen, subject to PoC performance). External endpoints only with written approval.

## Local Setup

```bash
# Dependencies
uv venv && uv pip install -r requirements.txt    # or: pip install -r requirements.txt

# Tests & quality
pytest
ruff check .
mypy libs pipelines app

# Run WS-1 on the sample (headless; the manifest is named by the config). Every run is
# recorded in the SQLite registry the admin monitor reads.
python -m pipelines.workstream1_sensitive --config config/ws1.yaml                 # batch
python -m pipelines.workstream1_sensitive --config config/ws1.yaml --source-id note_001  # single

# PoC web app (API-first; the UI is a client). Local, no auth — bind to loopback.
uvicorn app.main:app --host 127.0.0.1 --port 8000
#   /            hero (WS-1 / WS-2)          /ws1     source browser → single | batch
#   /ws1/live    interactive step-by-step    /jobs/<id>  results workbook
#   /admin       migration monitor (SSE)     /health  liveness
# WS-2 remains a placeholder (python -m pipelines.workstream2_matching --config config/ws2.yaml).
```

> The web app is a single FastAPI process: SQLite doubles as the durable job queue,
> drained by a worker thread. No Redis/Celery/Postgres in the PoC. Registry path via
> `WS1_REGISTRY_DB` (default `poc/registry.db`); config via `WS1_API_CONFIG`.

## System Contracts (see `CLAUDE.md`)

1. **Read-only source** — never modify a Prince Houston / Zendai record.
2. **Sensitive content is PII** — minimise it; no external inference without written approval.
3. **Explainable & auditable** — every flag/match carries a reason + evidence location + score type.
4. **Governed & reproducible** — frozen manifest + versioned config + run ledger.
5. **PoC discipline** — fixed scope on the sample; no production over-building.

## Working With Claude Code

This repo is configured for the **compound engineering** workflow:
**BRAINSTORM → PLAN → IMPLEMENT → REVIEW → COMPOUND**.

- Read `CLAUDE.md` for architecture and system contracts (the WHY).
- Read `AGENTS.md` for the workflow and approval gates (the HOW).
- Start work with `/project:brainstorm "<idea>"` then `/project:plan "<feature>"`.
- Enforcement rules live in `.claude/rules/`; solved problems in `docs/solutions/`.
- **Sourcing:** every new idea/fix is web-searched and either cited or explicitly
  labeled AI-generated — see `.claude/rules/citations.md`.

## Confidentiality

The RFP and our response (`docs/requirement/`) are confidential and for evaluation
only. No real records, samples, manifests with content, or truth sets containing PII
are ever committed to this repository.
