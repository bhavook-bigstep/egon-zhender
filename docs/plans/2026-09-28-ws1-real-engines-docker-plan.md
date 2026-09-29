# Plan: WS-1 Real Engines via Docker (resolve extraction/OCR + detection/AI)

- **Date:** 2026-09-28
- **Author:** Claude
- **Status:** done (Waves 1, 1b, 2, 3; optional PaddleOCR PP-Structure deferred)

## Intake Summary

```
Goal:        Take WS-1 rows 2 & 3 from "wired-against-fakes" to real engines that RUN
             locally: real native extraction (in-venv) + Docling/Tika/OCR + Presidio as
             Docker services, and the LLM via an external OpenAI-compatible API.
Workstream:  WS-1 (extract, ocr_gate, detect stages + their port adapters) + infra.
Inputs:      Same synthetic sample, enriched with a real small PDF/DOCX/XLSX + an image.
Sensitivity: Synthetic only. The LLM now leaves the boundary → Contract 2 is the
             load-bearing constraint.
Method:      ExtractionEngine (native | docling | tika) → OCR-gate → OCRProvider (http)
             → DetectionEngine (regex | presidio | presidio_http) → assess (external
             LLM API) → score/calibration. All behind existing ports, config-selected.
Output:      Same row schema; findings now from real engines. Docling adds page/table/
             cell locations.
Governance:  Versioned config selects engines + service URLs + model version; run
             ledger records which engine/model produced each run.
Constraints: Read-only source; INFERENCE EGRESS to a managed API is approval-gated +
             minimised (Contract 2 / §9.2); no secrets in repo; PoC time-box; the
             default skeleton path (mock/decode) stays working unchanged.
```

**PoC scope:** yes. Heavy engines run in containers (or in-venv for light ones); the
hermetic test suite keeps using fakes, with optional live tests that skip when a
container/endpoint is unreachable.

## Prior Learnings

- `docs/solutions/INDEX.md` — empty.
- Critical patterns: **#1 source mutation** (extractors post *copies* of bytes to
  services, never write source), **#2 content in logs** (service responses/errors routed
  through redaction; log source_id only), **#3 inference egress** — now front-and-centre:
  the external LLM API is off-boundary, so the gate (`is_local=false → crosses_boundary
  → requires approval_written`) plus minimisation (minimal span, no raw IDs) is mandatory.
- Ports already exist: `DetectionEngine` (detect.py), `OCRProvider` (ocr_gate.py),
  `InferenceProvider` (libs/inference). This plan adds an `ExtractionEngine` port and
  HTTP adapters; **no port redesign**.
- **Sources:**
  - Docling — https://github.com/docling-project/docling + pipeline options
    https://docling-project.github.io/docling/reference/pipeline_options/ (accessed 2026-09-28):
    parses PDF/DOCX/XLSX/images → structured Markdown/JSON with layout+tables, auto-gates
    OCR, pluggable OCR engines (RapidOCR/Tesseract/EasyOCR).
  - PaddleOCR PP-Structure — https://paddlepaddle.github.io/PaddleOCR/main/en/version2.x/ppstructure/overview.html
    (accessed 2026-09-28): OCR + layout + table→Excel (optional high-fidelity OCR).
  - Presidio — https://microsoft.github.io/presidio/ (accessed 2026-09-28): analyzer as a
    service with an /analyze REST API.
  - Apache Tika — https://tika.apache.org/ (accessed 2026-09-28): server extracts text
    from legacy .doc/.xls and many formats over HTTP (removes the host Java requirement).
  - LiteLLM / Bedrock — https://docs.litellm.ai/docs/providers/bedrock (accessed 2026-09-28):
    an OpenAI-compatible gateway routes to external APIs / self-hosted / Bedrock, so the
    LLM backend is a config swap. Our `OpenWeightProvider` already speaks this.
  - Native extractors: `pypdf`, `python-docx`, `openpyxl` (library docs) — light,
    pure-Python born-digital extraction. Trivial; no contested claim.
  - Docling-as-extractor + RapidOCR backend on 8 GB/no-GPU: **No source found — this is
    an AI-generated design choice** (composition decision; capabilities cited above).

## Approach

Add an `ExtractionEngine` port mirroring `DetectionEngine`, with engines selected by
config. Heavy engines are HTTP adapters to Docker services with an **injectable client**
(fake in tests). Light native extractors run in-venv and are tested for real. LLM stays
`OpenWeightProvider` pointed at an external API. The default committed config keeps
`mock`/`decode` so nothing egresses or requires containers unless explicitly selected.

Key decisions (confidence):
- **ExtractionEngine port + factory** (CERTAIN) — `decode` (current) | `native` |
  `docling` | `tika`.
- **Native extractor in-venv** (CERTAIN) — pdf→pypdf, docx→python-docx, xlsx→openpyxl.
- **Docling as the front door for scanned + rich layout** (PROBABLE) — HTTP; RapidOCR
  backend; self-gates OCR so our OCR-gate naturally skips when text is present.
- **OCRProvider HTTP adapter** for the native path's scanned pages (PROBABLE) — needs the
  image bytes, so `recognise(entry, data)` gains the bytes; `StubOCRProvider` ignores them.
- **Presidio over HTTP** (CERTAIN) — `presidio_http` engine → /analyze → map like the
  in-process `PresidioEngine`.
- **LLM via external API** (CERTAIN) — `provider: openweight`, `is_local: false`,
  `approval_written: true`, `api_key_env`; committed default stays `mock`.

**Contract check:** read-only (extractors send copies, never write source) ✓ · egress
(only the LLM leaves; approval-gated + minimal span + no raw IDs; OCR/detect/extract
services are local) ✓ · minimisation ✓ · explainable/scored (unchanged; Docling enriches
locations) ✓ · reproducible (engine/model/service versions in config + ledger; external
LLM greedy) ✓ · secrets (API key via env only) ✓.

## Tasks

| # | Task | Files | Depends on | Wave |
| - | ---- | ----- | ---------- | ---- |
| 1 | `ExtractionEngine` port + factory; refactor `extract.py` (current logic → `DecodeExtractor`) | `pipelines/workstream1_sensitive/extract.py`, `.../extract_engine.py` | — | 1 |
| 2 | `NativeExtractor` (pypdf/python-docx/openpyxl, in-venv) | `.../extract_native.py`, `libs/schemas.py` (ExtractConfig) | 1 | 1 |
| 3 | Light deps to base: `pypdf`, `python-docx`, `openpyxl`, `httpx` | `requirements.txt` | — | 1 |
| 4 | Enrich sample: real small PDF/DOCX/XLSX + image; extend fixture builder + truth | `tests/fixtures/build_ws1_sample.py`, `tests/fixtures/*` | 2 | 1 |
| 5 | `DoclingHttpExtractor` (injectable client) + `ocr` self-gating behaviour | `.../extract_docling.py` | 1 | 1 |
| 6 | `docker-compose.yml`: `docling` (+RapidOCR) service; Make/script targets; README | `docker-compose.yml`, `README.md`, `Makefile` | 5 | 1 |
| 7 | `PresidioHttpEngine` (injectable client) + factory `presidio_http` | `.../detect_presidio_http.py`, `detect.py`, `libs/schemas.py` (detect.presidio_url) | — | 2 |
| 8 | Add `presidio` service to compose | `docker-compose.yml` | 7 | 2 |
| 9 | `OcrConfig` + `HttpOcrProvider`; thread `data` into `OCRProvider.recognise` + `apply_ocr_gate` | `.../ocr_gate.py`, `.../ocr_http.py`, `runner.py`, `libs/schemas.py` | 1 | 3 |
| 10 | `TikaHttpExtractor` + `tika` service | `.../extract_tika.py`, `docker-compose.yml` | 1 | 3 |
| 11 | LLM external-API wiring: `config/ws1.docker.yaml` + egress-gate test; default stays mock | `config/ws1.docker.yaml` | — | 3 |
| 12 | Tests (fakes for all HTTP adapters; real native; optional live tests) | `tests/ws1/*` | 2,5,7,9,10 | each |
| 13 | Docs: WS-1 CLAUDE.md (row 2/3 runnable via containers; LLM external+approval) | `pipelines/workstream1_sensitive/CLAUDE.md`, root `CLAUDE.md` | — | each |
| 14 | (Optional) PaddleOCR PP-Structure service for high-fidelity tables | `docker-compose.yml`, `.../ocr_http.py` | 9 | opt |

## Tests

Hermetic (fakes) + optional live (skip when service/endpoint unreachable).

- [ ] `test_extract_native` — real tiny PDF/DOCX/XLSX (built in the fixture) extract to text + locations; recogniser hits on the synthetic tokens inside them.
- [ ] `test_extract_engine_factory` — decode | native | docling | tika selected; unknown → ValueError.
- [ ] `test_docling_extractor` (fake client) — service JSON → `ExtractedText` (text + `has_text_layer` true for a scanned page, so the OCR-gate skips).
- [ ] `test_presidio_http_engine` (fake client) — /analyze JSON → deterministic vs classifier `Finding`, category_map, unmapped skipped.
- [ ] `test_http_ocr_provider` (fake client) — image bytes POSTed → recognised text; service error → `OCR_FAILURE`.
- [ ] `test_tika_extractor` (fake client) — response text → `ExtractedText`.
- [ ] `test_llm_egress_gate` — `is_local=false` + `approval_written=false` → `InferenceEgressError`; only the minimal span (no raw identifiers) is in the request.
- [ ] `test_no_content_to_services` — extractor/OCR/detect requests + logs carry source_id + bytes only, never raw identifiers in logs; responses aren't logged verbatim.
- [ ] Optional live: `test_live_*` (importorskip/connect-skip) hit each container/endpoint.
- [ ] Regression: existing 67 pass on the default (decode/regex/mock) path.

## Risks & Rollback

- **8 GB RAM / no GPU** → stage services (Wave 1 docling, Wave 2 presidio, Wave 3 tika/ocr); LLM is external so no local model. Compose profiles per wave.
- **Accidental egress** → committed `config/ws1.docker.yaml` keeps LLM `mock` by default; `openweight` requires an explicit `base_url` + `approval_written: true` + env key.
- **Image tags / endpoint shapes drift** → the implement step verifies each service's real API; live tests are optional and skip otherwise.
- **Docling/torch pulls are large** → documented; Wave 1 only; native extractor works without any container for born-digital.
- **Rollback:** all additive (new files + compose + docker config); set engines back to `decode`/`regex`/`mock` and `docker compose down`. No source data touched.

## Review Notes

**Wave 1 (code-only) implemented 2026-09-28 — no image pulls.** Delivered: tasks 1–4 +
tests/docs. `ExtractionEngine` port + factory; `DecodeExtractor` (default) + real
`NativeExtractor` (pypdf/python-docx/openpyxl); ingest accepts DOCX/XLSX; runner uses the
engine; `config/ws1.yaml` `extract` block (default `decode`); light deps in
`requirements.txt` (+ `requirements-dev.txt` reportlab for the PDF fixture). Gates: ruff ✓,
mypy ✓ (33 files), pytest ✓ **73 passed + 2 skipped** (native DOCX/XLSX/PDF extraction run
for real). Default path unchanged.

**Wave 1b (Docling) implemented 2026-09-28.** `docker-compose.yml` (docling-serve-cpu,
:5001); `DoclingHttpExtractor` (`extract_docling.py`, injectable client); factory wired
(`engine: docling`); `config/ws1.docker.yaml`. **Live API verified against the running
container** — payload is `{sources:[{kind:file,…}], options:{to_formats:[text]}}` (the
adapter was corrected from the docs shape after checking `/openapi.json`), and a real
text conversion returned `document.text_content`. Gates: ruff ✓, mypy ✓ (34 files),
pytest ✓ **80 passed + 2 skipped** (the docling-live test now passes; only presidio/sbert
skip). Note: the current fake sample (`.pdf` is really UTF-8 text, `.png` is fake) isn't a
representative Docling e2e — a real-file manifest is the follow-up for a full run.

**Waves 2 & 3 implemented 2026-09-29.** `PresidioHttpEngine` (`detect.engine:
presidio_http`), `TikaHttpExtractor` (`extract.engine: tika`), `HttpOcrProvider`
(`ocr.provider: docling`; `OCRProvider.recognise` now takes `data`), and external-API LLM
wiring in `config/ws1.docker.yaml` (approval-gated, key via env). Compose adds `presidio`
(:3000) and `tika` (:9998). **Live APIs verified** against the running containers —
Presidio `/analyze` returns `{entity_type,start,end,score}` (adapter matches); Tika
`PUT /tika` returns text; the presidio/tika/docling live tests pass. Gates: ruff ✓,
mypy ✓ (37 files), pytest ✓ **93 passed + 2 skipped** (only in-process presidio/sbert
importorskips). Default path unchanged.

**Review fixes applied 2026-09-29** (6-agent review → CHANGES_REQUIRED, 4 P1). All P1 +
security/provenance/test P2 + cheap P3 fixed; gates ruff ✓, mypy ✓ (38 files), pytest ✓
**112 passed + 2 skipped**; live docling/presidio/tika tests pass against pinned,
loopback-bound containers. Fixes:
- **P1 egress minimisation** — `libs/minimisation.py` masks email/phone/LinkedIn with a
  keyed HMAC (`libs/hashing.hash_identifier`, EZ key via env) before any boundary-crossing
  `InferenceRequest`; fail-closed if the key is missing.
- **P1 Presidio-HTTP crash** — `PresidioHttpEngine` now raises typed `DETECTION_ERROR`;
  runner has an item-level `except` → `INTERNAL_ERROR` row (never aborts the batch).
- **P1 reproducibility** — compose images pinned by digest; `detector_version` from config;
  run ledger records an `engines` provenance block + a `stage="extract"` event.
- **P1 evidence locations** — `DetectionEngine.analyze(extracted)` + `resolve_location`
  map hits to page/sheet/cell via spans (native path); Docling page-anchoring via JSON
  remains a follow-up.
- **P2** — `InferenceConfig` boundary validator (fail closed on is_local vs base_url);
  services bound to `127.0.0.1` (Presidio host port → 3001); tests for native parser
  errors, `build_ocr`, and a `run()`-level native e2e.
- **P3** — `no_text_layer_result` public; shared `text_result` constructor; shared
  `build_convert_payload`; `DetectConfig.engine` comment; ADR `docs/adr/0001`.

**Still deferred (optional):** PaddleOCR PP-Structure; Docling JSON page-anchoring;
timeouts + `_MAX_SPAN_CHARS` → config; whole-file POST batching (production scale); a
real-file sample manifest for a full Presidio/Docling e2e (synthetic tokens aren't real
PII, so Presidio finds nothing on the fake sample — expected).
