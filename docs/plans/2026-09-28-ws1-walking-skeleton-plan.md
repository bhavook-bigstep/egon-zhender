# Plan: WS-1 Walking Skeleton Behind Ports (on the Sample Test Env)

- **Date:** 2026-09-28
- **Author:** Claude
- **Status:** approved

## Intake Summary

```
Goal:        Build a thin end-to-end WS-1 chain on our sample test env, with Source/
             LLM/Audit as stub adapters behind ports; prove one-row-per-input
             reconciliation + explainable rows; then deepen detect/assess/score.
Workstream:  WS-1 sensitive-data (+ shared libs for the three ports).
Inputs:      poc/sample/ synthetic file notes + documents behind a stub SourceReader.
             No client data, no Databricks this round.
Sensitivity: Synthetic only; pipeline obeys PII rules from day one (evidence by
             location; no content/raw IDs in logs or rows).
Method:      ingest -> extract (text layer) -> OCR-gate (decision real, engine stubbed)
             -> detect (deterministic recognisers) -> assess (mock LLM provider) ->
             score/band -> one output row.
Output:      ws1_item_summary + ws1_findings rows per response §3.4 (status, category,
             reason, evidence LOCATION, score_type/band, calibration_status, exception).
Governance:  Frozen sample manifest + versioned config + run ledger + reconciliation;
             deterministic (sorted + seeded).
Constraints: Read-only source; controlled inference (mock/local only); explainable +
             scored; reproducible; PoC time-box. Ports stay stable so later hardening
             (Audit -> multi-LLM -> input bin) is a drop-in adapter swap.
```

**PoC scope:** yes. This proves the WS-1 method + contracts on a controlled sample.
Production scale-out, real Databricks, multi-provider routing, and production audit are
explicitly deferred (Contract 5).

## Prior Learnings

- `docs/solutions/INDEX.md` — empty; no prior WS-1 work to reuse.
- `.claude/rules/critical-patterns.md` — three incident patterns apply directly:
  (1) source mutation → SourceReader is read-only, no write path; (2) sensitive content
  in logs → all logging routes through `libs/audit/redaction.py`; (3) inference egress →
  skeleton uses a local MockProvider; the `InferenceProvider` port carries an
  approval-gate flag for later.
- `pipelines/workstream1_sensitive/CLAUDE.md:14-24` — fixes the 7-stage sequence and the
  required output fields; this plan implements exactly that, thinly.
- Response §3.2 (decision rules FLAGGED / NOT_FLAGGED / UNABLE_TO_PROCESS + PARTIAL),
  §3.3 (score types + 0-100 scale + calibration_status + bands), §3.4 (ws1 table fields)
  — the row schema below is taken from these.
- **Sources for novel decisions:**
  - Walking skeleton — 97 Things Every Software Architect Should Know (O'Reilly) —
    https://www.oreilly.com/library/view/97-things-every/9780596800611/ch60.html
    (accessed 2026-09-28): thinnest end-to-end slice linking all components.
  - Hexagonal / Ports & Adapters — Bitloops —
    https://bitloops.com/resources/software-architecture/hexagonal-architecture
    (accessed 2026-09-28): swap stub/real adapters per port without touching core logic.
  - Presidio recognizers (deepen phase) —
    https://microsoft.github.io/presidio/analyzer/adding_recognizers/ (accessed 2026-09-28).
  - OCR-gate heuristic (OCR only when no/poor text layer) — Apify born-digital PDF —
    https://apify.com/scrapesage/ocr-text-extractor/examples/ocr-pdf-text-layer-fast-extraction
    (accessed 2026-09-28). The specific quality-metric set (text density + printable
    ratio + image coverage) and thresholds: **No source found — this is an AI-generated
    idea** — defaults, to be calibrated in the PoC.
  - Deterministic MockProvider scoring for the skeleton: **No source found — this is an
    AI-generated idea** (standard test double).

## Approach

Two phases. **Phase 1 (skeleton)** lays every stage thin and wires the three ports with
stub adapters, proving the contracts on `poc/sample/`. **Phase 2 (deepen core)** thickens
detect/assess/score — the part the PoC is judged on — keeping extraction/OCR robustness
and the surrounding-parts order (Audit -> multi-LLM -> input bin) as *later* plans.

**Layout (new files):**

```
libs/
  schemas.py          # pydantic models + enums (row/finding/manifest/config)   [CERTAIN]
  config.py           # load + validate versioned YAML config; expose seed       [CERTAIN]
  source/base.py      # SourceReader Protocol (read-only)                        [CERTAIN]
  source/sample.py    # SampleTestEnvReader adapter                              [CERTAIN]
  inference/base.py   # InferenceProvider Protocol + approval-gate contract      [CERTAIN]
  inference/mock.py   # MockProvider (deterministic, local)                      [PROBABLE]
  audit/redaction.py  # redact() — source_id + location only                     [CERTAIN]
  audit/ledger.py     # RunLedger: record_stage_event(), reconcile()            [CERTAIN]
pipelines/workstream1_sensitive/
  ingest.py extract.py ocr_gate.py detect.py assess.py score.py output.py
  runner.py __main__.py
config/ws1.yaml
poc/sample/…  poc/ws1_manifest.json  poc/ws1_truth.json
tests/ws1/…  tests/libs/…
requirements.txt (or pyproject) — pytest, ruff, mypy, pydantic, pyyaml
```

**Port contracts (the seams that keep your order cheap):**
- `SourceReader`: `list_manifest() -> list[ManifestEntry]`, `open_item(source_id) -> BinaryIO`
  (read-only, no write method exists). [CERTAIN]
- `InferenceProvider`: `assess(req: InferenceRequest) -> InferenceResult`; implementations
  must refuse when `req.crosses_boundary and not config.inference.approval_written`. [CERTAIN]
- `RunLedger`: append-only stage events + `reconcile()` asserting
  `inputs == flagged + not_flagged + unable_to_process`. [CERTAIN]

**Skeleton stage depth (Phase 1):** extract = text-layer/plain-text only; ocr_gate =
real decision logic, OCR engine call via a stubbed `OCRProvider`; detect = a couple of
regex/checksum recognisers with rule IDs; assess = MockProvider; score = real band/flag
logic. **Deepen (Phase 2):** detect -> Presidio recognisers; assess -> semantic screen +
real open-weight model behind the same port; score -> calibration_status logic.

**Config keys / thresholds (`config/ws1.yaml`, all versioned — no literals in code):**
`config_version`, `seed: 1729`, `source.backend: sample`, `inference.provider: mock`,
`inference.approval_written: false`, `ocr_gate.{min_text_density,min_printable_ratio,
max_image_coverage}`, `taxonomy.{version,categories}`, `scoring.{flag_threshold, bands:
{high,medium,low}}` (0-100 per §3.3), `output.{result_dir,format: jsonl}`.

**Contract check:** read-only (no write path on SourceReader) ✓ · minimisation +
controlled inference (local MockProvider; approval-gate on the port) ✓ · explainable
(every row carries reason + evidence_location + score_type; deterministic findings carry
rule_id, AI findings carry score + band + calibration_status) ✓ · reproducible (frozen
manifest + config_version + seed + ledger + sorted output) ✓.

## Tasks

| # | Task | Files | Depends on | Parallel? |
| - | ---- | ----- | ---------- | --------- |
| 1 | Schemas + enums (Ws1Row, Finding, ManifestEntry, FlagStatus, ScoreType, Band, ExceptionCode, calibration_status) | `libs/schemas.py` | — | no (foundation) |
| 2 | Config loader + validation + seed | `libs/config.py`, `config/ws1.yaml` | 1 | yes |
| 3 | Ports: SourceReader, InferenceProvider, RunLedger, redaction | `libs/source/base.py`, `libs/inference/base.py`, `libs/audit/ledger.py`, `libs/audit/redaction.py` | 1 | yes |
| 4 | Stub adapters: SampleTestEnvReader, MockProvider, JSONL ledger sink | `libs/source/sample.py`, `libs/inference/mock.py` | 3 | yes |
| 5 | Sample env + frozen manifest + truth set (synthetic: 2 notes, 1 born-digital doc, 1 image-only doc, 1 unreadable) | `poc/sample/*`, `poc/ws1_manifest.json`, `poc/ws1_truth.json` | 1 | yes |
| 6 | Stages: ingest, extract, ocr_gate | `pipelines/workstream1_sensitive/{ingest,extract,ocr_gate}.py` | 3,4 | yes |
| 7 | Stages: detect, assess, score | `pipelines/workstream1_sensitive/{detect,assess,score}.py` | 3,4 | yes |
| 8 | Output assembly + reconciliation | `pipelines/workstream1_sensitive/output.py` | 1,3 | no |
| 9 | Runner + `__main__` (deterministic orchestration, typed per-item exceptions) | `pipelines/workstream1_sensitive/{runner,__main__}.py` | 6,7,8 | no |
| 10 | Tooling: requirements + ruff/mypy config | `requirements.txt`, `pyproject.toml` | — | yes (early) |
| 11 | Tests (see below) | `tests/ws1/*`, `tests/libs/*` | 9 | partly |
| 12 | Fix CLAUDE.md command placeholder to real entry point | root `CLAUDE.md` Commands note | 9 | no |

Parallel waves: **W1** = {1,10}; **W2** = {2,3,5}; **W3** = {4,6,7}; **W4** = {8}; **W5** = {9}; **W6** = {11,12}.

## Tests

Synthetic fixtures only; mock Source/LLM/OCR boundaries; deterministic.

- [ ] `test_ingest` — item not in manifest → blocked; hash mismatch → `HASH_MISMATCH` exception row.
- [ ] `test_extract` — born-digital text extracted; empty text → coverage flag set.
- [ ] `test_ocr_gate` — has good text layer → OCR skipped; no/poor layer → OCR path taken; gate decision + quality measure recorded.
- [ ] `test_detect` — recogniser hit returns finding with `rule_id` + `evidence_location`; miss returns none; no content string in the finding.
- [ ] `test_assess` — MockProvider returns `MODEL_SCORE`; `calibration_status = NOT_CALIBRATED` (no truth set yet).
- [ ] `test_score` — band boundaries (flag_threshold / low / medium / high) and flag_status decision (FLAGGED / NOT_FLAGGED / UNABLE_TO_PROCESS + PARTIAL) at edges.
- [ ] `test_output_reconcile` — inputs == flagged + not_flagged + unable_to_process; exactly one summary row per input.
- [ ] `test_redaction` — ledger + rows + logs contain no document text / evidence text / raw identifiers (only source_id + location).
- [ ] `test_reproducibility` — same manifest + config + seed → byte-identical sorted output.
- [ ] `test_inference_gate` — provider refuses when `crosses_boundary` and `approval_written = false`.
- [ ] `test_end_to_end` — full skeleton over `poc/ws1_manifest.json` → rows match `poc/ws1_truth.json`; ledger reconciles.

Target ~90% on changed lines, prioritising exception paths and score/threshold logic.

## Risks & Rollback

- **Skeleton feels featureless early** → the e2e + reconcile test is the milestone; demo it before deepening.
- **Loose extract→detect contract** (Approach C's risk) → `ExtractResult` (text-by-location + coverage) is defined in `libs/schemas.py` in Task 1, before stages.
- **Heavy deps creep into the skeleton** → Phase 1 stays std-lib + pydantic/pyyaml; Presidio/OCR/model libs enter only in Phase 2.
- **Rollback:** all work is new files under `libs/`, `pipelines/`, `poc/`, `tests/`, `config/`; delete the directories to revert. No source data touched; nothing committed until you approve.

## Review Notes

**Implemented + reviewed 2026-09-28.** Six-agent review → verdict CHANGES_REQUIRED on
one P1; fixed the recommended bundle (P1 + cheap P2/P3s). Gates: ruff ✓, mypy ✓ (25
files), pytest ✓ **41 passed**.

Applied:
- **P1** run ledger now persisted → `ws1_run_ledger.json` (`output.write_ledger`,
  content-free; reconcile + stage events + final_status). Tests assert it exists,
  reconciles, is reproducible, and leaks no content.
- **P2** removed dead `band_low`; `reason_summary` cites `rule_id` for deterministic
  findings; added `SourceReader.open_stream` (streaming read path for the 55 GB corpus);
  moved `sha256_hex` to `libs/hashing.py` (ingest no longer imports a concrete adapter);
  new tests for the `UNREADABLE`/`OSError` path, OCR-failure-through-runner, `assess`
  empty-text, and the flag-threshold `==` boundary.
- **P3 (quality)** removed dead `random.seed`; de-duplicated the no-text-layer builder
  (`_no_text_layer`); made `printable_ratio`/`line_spans` public (no cross-module private
  import); `write_outputs` validates `output.format`.
- **Deferred P3s** recorded in `pipelines/workstream1_sensitive/CLAUDE.md` (OCR/audit port
  parity, span-limit/threshold_version→config, egress fail-safe, production streaming +
  timeouts, extra coverage).
```
Deferred to later plans (your stated order), once the skeleton is proven:
  Phase 2  — deepen detect (Presidio) / assess (semantic + open-weight LLM) / calibration
  Then     — Part 5 Audit hardening -> Part 4 multi-LLM provider -> Part 1 input bin (Databricks)
  Also     — real extraction (docx/xlsx/Docling) + PaddleOCR engine behind the OCR port
```
