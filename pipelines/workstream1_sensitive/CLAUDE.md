# Workstream 1 — Sensitive-Data Identification — CLAUDE.md

Inherits: root `CLAUDE.md` (contracts, anti-patterns), `.claude/rules/data-pipeline.md`,
`.claude/rules/privacy-sensitive-data.md`, `.claude/rules/matching-scoring.md`,
`.claude/rules/security.md`, `.claude/rules/performance.md`, `.claude/rules/testing.md`.

## Purpose

Assess every authorised file note and document against the approved taxonomy and
emit one explainable output row per item. The mandatory service is **automated
scanning and flagging**; human validation is a separately-priced option activated
only in writing. Source content is read-only and never modified.

## Processing Sequence

```
1 Ingest    Read-only Databricks tables/volumes; MIME detect; SHA-256 content hash → frozen manifest
2 Extract   Native (PDF/DOCX/XLSX) · Apache Tika (legacy DOC/XLS) · Docling (layout/tables); no macros/active content
3 OCR gate  PaddleOCR only where the text layer is absent or fails quality (density, printable ratio, image coverage)
4 Detect    Presidio + custom checksum-/context-validated recognisers on readable content
5 Assess    Semantic screening + LLM (baseline Qwen, PoC-validated) for contextual categories
6 Score     Deterministic (rule ID) vs AI/probabilistic (score + band + calibration status)
7 Output    One row per item: status, category, reason, evidence location, score, exception code
```

## Required Output Fields (per RFP)

Source record identifier · content type · available metadata (author, date/time,
linked Executive, linked project) · flag status (`flagged / not_flagged /
unable_to_process`) · sensitivity category · reason for flag · confidence score +
scale (where AI/probabilistic) · processing exception (where applicable).

## WHY This Sequence

- **OCR is gated** because it is the expensive stage; most born-digital files have a
  good text layer and must not be re-OCR'd (root Contract 4 + performance).
- **Deterministic first, AI second** so a checksum/rule match is labelled as fact and
  only ambiguous content reaches the model — smaller prompts, less egress, calibratable
  scores (root Contract 3).
- **Evidence by location, not content** so findings are auditable without leaking PII
  (root Contract 2).

## Key Files and Locations (once scaffolded)

| Component      | Location                     | Description                              |
| -------------- | ---------------------------- | ---------------------------------------- |
| Ingest/manifest| `ingest/`                    | Read-only access, hashing, frozen manifest |
| Extraction     | `extract/`                   | Native + Tika + Docling routing          |
| OCR gate       | `ocr/`                       | Gate decision + PaddleOCR + quality measure |
| Detection      | `detect/`                    | Presidio + custom recognisers            |
| Assessment     | `assess/`                    | Semantic + LLM contextual scoring        |
| Output/ledger  | `output/`                    | Row assembly + run ledger + reconciliation |

## Testing

pytest with **synthetic** fixtures. Cover parser exceptions, OCR-gate branches,
recogniser hits/misses, `unable_to_process`, scoring/band logic, and one-row-per-input
reconciliation. Mock Databricks, OCR, and the model. Assert logs/outputs carry no
sensitive content.

## Phase 2 — core deepening (implemented 2026-09-28)

Behind the existing ports, config-selected; heavy engines lazy-imported so the skeleton
path (`engine: regex`, `provider: mock`, no calibration) and the hermetic test suite stay
light. Real engines need `requirements-ml.txt` (+ an endpoint for the LLM).

- **Detect:** `DetectionEngine` factory — `RegexEngine` (default) | `PresidioEngine`
  (checksum/validated → DETERMINISTIC_MATCH; NER → CLASSIFIER_SCORE).
- **Assess:** `SemanticScreen` (SBERT, SIMILARITY + routes what reaches the LLM) +
  `OpenWeightProvider` (OpenAI-compatible, structured output, greedy). Egress now
  fail-safe: `crosses_boundary` is derived from `provider.is_local`.
- **Score:** `libs/calibration.py` — sigmoid/isotonic/identity mapping + §3.3
  `calibration_status`; versioned artefact applied by the runner (`finalize_scored`).

## Real engines — Wave 1 (extraction, 2026-09-28)

- `ExtractionEngine` port + factory (`extract_engine.py`); `DecodeExtractor` (default),
  **`NativeExtractor`** (real born-digital: `pypdf`/`python-docx`/`openpyxl`), and
  **`DoclingHttpExtractor`** (`extract_docling.py`) → docling-serve container. Config
  `extract.engine: decode | native | docling` (docling needs `extract.docling_url`).
- **docling-serve-cpu** runs via `docker compose up -d docling` (:5001). Verified live
  API: `POST /v1/convert/source` with `{sources:[{kind:file,base64_string,filename}],
  options:{to_formats:[text]}}` → `document.text_content`. Docling OCRs scanned pages
  internally, so it is the extract + OCR front door. `config/ws1.docker.yaml` selects it.
## Real engines — Waves 2 & 3 (2026-09-29)

- **Detection:** `PresidioHttpEngine` (`detect_presidio_http.py`) → presidio container
  `POST /analyze`; `detect.engine: presidio_http` + `detect.presidio_url`. Shares the
  entity→finding mapping with the in-process engine.
- **Legacy extraction:** `TikaHttpExtractor` (`extract_tika.py`) → tika container
  `PUT /tika`; `extract.engine: tika` + `extract.tika_url` (.doc/.xls, no host Java).
- **OCR:** `HttpOcrProvider` (`ocr_http.py`) reuses the docling service as the OCR backend;
  `ocr.provider: docling` + `ocr.url`. `OCRProvider.recognise(entry, data)` now takes bytes.
- **LLM:** external OpenAI-compatible API via `OpenWeightProvider` — config only
  (`config/ws1.docker.yaml` example): `is_local: false` + `approval_written: true` +
  `api_key_env`. Egress is gated (Contract 2); a LiteLLM proxy fronts self-hosted/Bedrock.
- Compose services: `docling` (:5001), `presidio` (:3000), `tika` (:9998). Live APIs
  verified against the running containers. Optional PaddleOCR PP-Structure remains a
  follow-up. Plan: `docs/plans/2026-09-28-ws1-real-engines-docker-plan.md`.

## Jobs (single-job path, 2026-09-29)

- Job schema in `libs/jobs.py`: `JobRequest` (job_type single|batch, config_version,
  source_ids, batch hints) → `JobResult` (uniform: status, run_id, reconcile,
  item_statuses, result paths, inline rows for single). Both modes **select from the
  frozen manifest by source_id** — same governance as a full run.
- Shared core: `runner.build_context()` (warm deps) + `runner.process_item()`; `run()`
  (batch) and `job_runner.run_single()` both call it, so single/bulk can't drift.
- `run_single(config_path, JobRequest)` — low-latency, writes a **job-namespaced** result
  set (`<result_dir>/single-<run_id>/`), returns rows inline. CLI: `--source-id <id>`.
- `run_batch(config_path, JobRequest)` — whole/selected manifest with **bounded
  concurrency** (`max_concurrency`, thread pool; per-item local ledgers merged
  deterministically), **checkpointing** (`batch_size`) and **resume** (`resume=True`
  skips source_ids already final in the prior ledger). Output is **namespaced per run**
  (`<result_dir>/batch-<run_id>/`), so distinct selections never clobber each other and
  resume reads only THIS run's partial. Because `run_id` = f(selection + config + seed),
  resume is self-gating: it only picks up a prior partial of the *identical* selection +
  config, then intersects with the current selection. Output sorted → identical bytes
  regardless of completion order. CLI: `--batch [--max-concurrency N] [--resume]`.
- **Interactive view:** `job_service.run_interactive()` runs `run_single` in a worker
  thread with an `on_event` hook that streams stage events over a queue (SSE), then emits
  the finished rows + result — no duplicate single-job orchestration path.
- Deferred for production scale: streamed/append writes instead of full-set rewrite per
  checkpoint; async/pollable `Job` store; per-service concurrency caps.

## Web app — operator UI + admin monitor (2026-09-29)

- **One FastAPI process, API-first** (`app/main.py`): the CLI, the API and the UI all
  share `JobService` + the SQLite registry, so a headless run is visible in the admin
  monitor. Local/no-auth — bind to `127.0.0.1`. Run: `uvicorn app.main:app`.
- **Pages** (server-rendered Jinja + vendored HTMX + native SSE; no CDN, no build step):
  `/` hero (WS-1 active, WS-2 placeholder) · `/ws1` metadata-only source browser
  (checkbox select → **single** = interactive live view, or **batch** = queued) ·
  `/ws1/live` SSE stage timeline + result row · `/jobs/<id>` results workbook (reconcile
  banner, provenance, per-row drill to findings + evidence **location**, status filter) ·
  `/admin` migration tiles + jobs table (cancel/retry) streamed over `/api/admin/stream`.
- **Privacy:** every surface is metadata-only — the browser drops `content_hash` and
  `path`; findings show category / score_type / band / evidence **location**, never the
  matched string, OCR text, or raw identifiers. Tests assert no content leak in any page.
- **Approval gate surfaced:** the `/ws1` submit screen shows a warning banner when the
  selected config points at a managed model (`is_local: false`); the pipeline gate +
  config validator still enforce Contract 2.
- **Admin completion is clamped to 100%** (`libs/registry.py`): `processed` sums per-job
  counts, so re-running an item (e.g. an interactive single over an id a batch covered)
  double-counts. Distinct-item accounting would need per-run source_id sets — deferred;
  raw counts stay truthful, only `pct_complete` is clamped.
- Plan: `docs/plans/2026-09-29-ws1-poc-ui-plan.md` (supersedes the API-only
  `2026-09-29-ws1-api-registry-admin-plan.md`).

## Still deferred (review 2026-09-28)

- **Port parity:** relocate `OCRProvider` to `libs/ocr/base.py` + config-swappable
  `build_ocr`; optional `AuditLedger` protocol.
- **Config over literals:** move `_MAX_SPAN_CHARS` (assess) into config; populate
  `Finding.threshold_version` for MODEL/CLASSIFIER findings (SIMILARITY already carries it).
- **Performance (production):** streamed/checkpointed output writes instead of an
  in-memory global sort at ~420k rows. (Done: `SourceReader.open_stream` read side;
  `HttpChatClient` timeout on the LLM call.)
