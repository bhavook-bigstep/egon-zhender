# Plan: WS-1 PoC gap closure — calibration, checksum recognisers, adjudication, OCR preprocessing

- **Date:** 2026-09-30
- **Author:** Claude
- **Status:** draft

## Intake Summary

```
Goal:        Close four WS-1 method/auditability gaps on the controlled sample —
             (1a) fit+apply real score calibration from the golden truth, (2) custom
             checksum-validated recognisers, (6a) a human review/adjudication flow,
             (5a) OCR image-preprocessing so heavy scans stop failing.
Workstream:  WS1 sensitive-data + shared libs (app UI). No WS2.
Inputs:      Frozen golden truth (datasets/ws1_golden) + the Databricks source; a
             completed WS-1 run's output rows/findings for calibration + review.
Sensitivity: All PII (financial/government_id/health). Checksums + reveal touch the
             matched value transiently, in-boundary, never persisted/logged.
Method:      Calibration (Platt/isotonic) · deterministic checksum recognisers ·
             gated OCR preprocessing (deskew/denoise/binarize) · HITL adjudication.
Output:      Calibrated scores + calibration_status; deterministic findings for
             checksum-valid IDs; recovered text for hard scans; per-record review
             decision + audit trail; §3.4 export augmented with review columns.
Governance:  Versioned calibration artefact (config-referenced); reviews in a SEPARATE
             SQLite store (never mutate source); deterministic dev/holdout split (seed);
             every finding still explainable + scored (Contracts 1–5).
Constraints: Read-only source; minimise + never persist matched content; open-weight /
             in-boundary only; PoC time-box; no over-building (Contract 5).
```

**Scope decisions (adjust at the gate):**
- **1a** — the golden set is ~48 docs, so per-category positives are < 100 → the honest outcome is **`PROVISIONAL`, not `CALIBRATED`** (per §3.3's ≥100-positives rule). We prove the *mechanism* end to end and report reliability; reaching `CALIBRATED` needs a larger truth set. (CERTAIN)
- **6a** — the response frames human validation as a *separately-priced option activated in writing*. We build it as a **PoC demonstration of that option**, not a contractual activation. (PROBABLE — confirm this framing is acceptable.)
- **5a** — designed to actually recover the failing **heavy image-only PDFs** (gold-0012/0033), which needs PDF **rasterisation** before preprocessing. Adds optional deps (`pypdfium2`, `scikit-image`) to `requirements-ml.txt`, lazy-imported. (CERTAIN)

## Prior Learnings

**Internal (verified this session, learnings-researcher + direct reads):**
- **Calibration is mostly wiring.** `libs/calibration.py` (`fit_calibrator`, `calibration_error`) implements §3.3 exactly; `pipelines/workstream1_sensitive/calibrate.py` is a CLI that fits from a `{category: {split: [(score,label)]}}` JSON. `runner.build_calibrator` loads `cfg.scoring.calibration.artefact` (all configs ship `null` → `NOT_CALIBRATED`); `score.finalize_scored` already applies it. **Missing:** a producer that turns `datasets/ws1_golden/{manifest,labels}.jsonl` + a run's findings into that labels structure.
- **Checksum genuinely unbuilt.** `detect_presidio.map_presidio_results:44` maps `deterministic_entities` → `DETERMINISTIC_MATCH` but runs no checksum; `CREDIT_CARD`'s Luhn happens *inside* Presidio. No `luhn/mod-97/aba` anywhere. `CustomRecogniserConfig`/`StoredRecognizer` have a `deterministic` flag but no validator.
- **Review unbuilt.** Nothing persists a reviewer decision; `Finding` has no `review_status` (a stale brainstorm claim). Only the read-only lazy reveal (`/api/jobs/{id}/reveal`) exists. Approach B was *selected* 2026-09-29 but deferred to "Phase 3".
- **OCR is ADR'd.** `docs/adr/0001` — Docling is the front door, PaddleOCR is an *optional* backend; `OcrConfig.provider` is `stub|docling`; `ocr_gate.apply_ocr_gate` calls `ocr.recognise` when `needs_ocr`. Heavy PDFs: docling extract → 0 chars → gate → stub raises `OCR_FAILURE`.
- Reuse the SQLite+SSE UI shell pattern (`docs/solutions/patterns/ws1-web-ui-sse-sqlite-queue.md`) and the metadata-only / gated-reveal rules (critical-patterns #2, #4).

**Sources (external, web-searched):**
- Platt for small sets — [Better Classifier Calibration for Small Data Sets — arXiv — https://arxiv.org/pdf/2002.10199](https://arxiv.org/pdf/2002.10199) (accessed 2026-09-30): parametric calibration resists overfit on small sets; isotonic needs ~≥100/class.
- Platt guidance — [The Complete Guide to Platt Scaling — Train in Data — https://www.blog.trainindata.com/complete-guide-to-platt-scaling/](https://www.blog.trainindata.com/complete-guide-to-platt-scaling/) (accessed 2026-09-30): calibrate on a held-out set; isotonic overfits below ~100 obs.
- Checksum recognisers — [Adding recognizers — Microsoft Presidio — https://microsoft.github.io/presidio/analyzer/adding_recognizers/](https://microsoft.github.io/presidio/analyzer/adding_recognizers/) (accessed 2026-09-30): `validate_result` (Luhn etc.); True → trust, False → drop/lower.
- OCR preprocessing — [Advanced Image Processing Techniques — Dynamsoft — https://www.dynamsoft.com/blog/insights/image-processing/advanced-image-processing-techniques-in-document-scanning-sdks/](https://www.dynamsoft.com/blog/insights/image-processing/advanced-image-processing-techniques-in-document-scanning-sdks/) (accessed 2026-09-30): deskew → denoise → adaptive binarize; +10–30% accuracy; deskew before binarize.
- HITL adjudication — [Human-in-the-Loop AI: Enterprise Governance — Tungsten — https://www.tungstenautomation.com/blog/human-in-the-loop-ai-enterprise-governance-best-practices](https://www.tungstenautomation.com/blog/human-in-the-loop-ai-enterprise-governance-best-practices) (accessed 2026-09-30): route → reviewer decides with rationale → decision logged to audit trail; uncertainty sampling picks lowest-confidence items first.
- Library choices (`pypdfium2` rasteriser + `scikit-image` `threshold_sauvola`/deskew): **No source found — this is an AI-generated idea** (standard tools chosen to implement the cited technique without system deps).

## Approach

Four independent workstreams behind existing ports; heavy/optional deps lazy-imported so the hermetic suite stays light. A→C has a soft dependency (uncertainty sort reads calibrated confidence, falls back to raw).

### A. Calibration wiring (1a) — CERTAIN
Produce `labels_by_category` from a completed run + golden truth, fit via the existing `fit_calibrator`, apply via the existing runner path.
- **NEW `libs/eval/calibration_labels.py`** — `build_labels(results, findings, truth, *, holdout_frac=0.4, seed) -> dict[str, dict[str, list[tuple[float,int]]]]`: for each finding carrying a numeric `score` (CLASSIFIER_SCORE/MODEL_SCORE), pair `(raw_score, label)` where `label = 1` if the finding's category ∈ the source's `expected_categories` (golden truth) else `0`; sort deterministically and split dev/holdout by `seed`. Content-free (scores + labels only).
- **NEW `pipelines/workstream1_sensitive/calibrate_from_golden.py`** — CLI: read a run's `ws1_findings.jsonl` + `WS1_GOLDEN_DIR`, call `build_labels`, then `fit_calibrator(method="sigmoid")`, write `config/ws1_calibration.json`. Reuses `calibrate.py`'s writer.
- **Config** — `config/ws1.databricks.yaml`: `scoring.calibration.artefact: config/ws1_calibration.json`, `method: sigmoid`, keep `min_positives`/`max_holdout_error`. (config-over-literals; Contract 4)
- **Eval page** — add a small `calibration` block to `/api/admin/eval` (counts by `calibration_status`) so reliability is visible. Minimal.

### B. Checksum-validated recognisers (2) — CERTAIN
Run a validator on the matched span in *our* code (works for both the in-process and HTTP Presidio paths); a pass makes the finding deterministic, a fail drops it. Also document enabling Presidio's built-in Luhn (2A) via `deterministic_entities: [CREDIT_CARD]`.
- **NEW `libs/checksums.py`** — pure fns `luhn(s)`, `iban_mod97(s)`, `aba_routing(s)`; `VALIDATORS: dict[str, Callable[[str], bool]]`. No PII persisted; operate on the passed substring only.
- **Schema** — add `validator: str | None` to `CustomRecogniserConfig` (`libs/schemas.py`) and `StoredRecognizer` (`libs/recognizers_store.py`), validated ∈ `VALIDATORS` (or None).
- **`detect_presidio.map_presidio_results`** — add params `text: str` and `validators: dict[str,str]`; for an entity with a validator, run it on `text[start:end]` → pass ⇒ emit `DETERMINISTIC_MATCH` (rule_id `f"{entity}:{validator}"`); fail ⇒ skip the finding. Both `PresidioEngine.analyze` and `PresidioHttpEngine.analyze` pass `extracted.text` + a `validators` map built from `cfg.custom_recognizers`.

### C. Human review / adjudication (6a) — PROBABLE
A separate, append-only review store + workbook controls; uncertainty-ordered.
- **NEW `libs/review_store.py`** — `ReviewStore` over SQLite (own tables in the registry DB): `reviews` (source_id PK, job_id, status ∈ pending/accepted/rejected/needs_info, reviewer, rationale, calibrated_score, decided_at) + append-only `review_events` (audit trail). Read-only w.r.t. source.
- **`app/main.py`** — `GET /api/admin/reviews` (current review state, merged into the latest-per-record view), `POST /api/admin/reviews` (record a decision; reviewer = `userEmail`); augment the §3.4 export (`_EXPORT_COLUMNS`/`_export_cell`) with `review_status/reviewer/rationale/decided_at`.
- **Workbook** (`admin_workbook.html` + `app.js`) — per-record accept/reject/needs-info + rationale field; a "review queue" sort **lowest calibrated confidence first** (uncertainty sampling), and a status filter. Metadata-only surface; rationale is reviewer-authored (guidance: reference by location, don't paste source PII).

### D. OCR preprocessing (5a) — CERTAIN
A real preprocessing OCR provider behind the `OCRProvider` port, selected by config; delegates recognition to the existing docling backend.
- **NEW `pipelines/workstream1_sensitive/ocr_preprocess.py`** — `preprocess_image(data: bytes) -> bytes` = grayscale → deskew (projection-profile angle → rotate) → median denoise → adaptive binarise (`threshold_sauvola`); lazy `PIL`/`numpy`/`skimage`. `rasterize_pdf(data, dpi) -> list[bytes]` via lazy `pypdfium2`.
- **NEW `pipelines/workstream1_sensitive/ocr_preprocess_provider.py`** — `PreprocessOcrProvider(OCRProvider)`: PDF ⇒ rasterize → preprocess each page → OCR via an injected docling `ConvertClient` (reuse `HttpOcrProvider`/`extract_docling`), concat; image ⇒ preprocess → OCR. Injectable clients → hermetic tests.
- **Schema/runner** — `OcrConfig`: add `provider: preprocess`, `url`, `dpi: int = 200`, `preprocess: {deskew, denoise, binarize}` toggles; `runner.build_ocr` gets a `preprocess` branch.
- **Config** — `config/ws1.databricks.yaml`: `ocr.provider: preprocess`, `ocr.url: http://localhost:5001`.
- **`requirements-ml.txt`** — `pypdfium2`, `scikit-image` (lazy; not in the base install).

## Tasks

| # | Task | Files | Depends on | Parallel? |
| - | ---- | ----- | ---------- | --------- |
| A1 | `build_labels` producer | `libs/eval/calibration_labels.py` | — | yes |
| A2 | Golden calibration CLI | `pipelines/workstream1_sensitive/calibrate_from_golden.py` | A1 | no |
| A3 | Config artefact + eval calibration block | `config/ws1.databricks.yaml`, `app/main.py`, `app/static/app.js` | A2 | no |
| B1 | Checksum validators | `libs/checksums.py` | — | yes |
| B2 | `validator` field + validation | `libs/schemas.py`, `libs/recognizers_store.py` | B1 | no |
| B3 | Apply validator in both engines | `detect_presidio.py`, `detect_presidio_http.py` | B2 | no |
| C1 | Review store | `libs/review_store.py` | — | yes |
| C2 | Review API + export cols | `app/main.py` | C1 | no |
| C3 | Workbook review UI (uncertainty sort) | `admin_workbook.html`, `app/static/app.js` | C2, A3 (soft) | no |
| D1 | Preprocess + rasterize | `pipelines/workstream1_sensitive/ocr_preprocess.py`, `requirements-ml.txt` | — | yes |
| D2 | Preprocess OCR provider | `pipelines/workstream1_sensitive/ocr_preprocess_provider.py` | D1 | no |
| D3 | OcrConfig + build_ocr + config | `libs/schemas.py`, `runner.py`, `config/ws1.databricks.yaml` | D2 | no |

Parallel front: **A1, B1, C1, D1** (independent). Then each chain proceeds; C3 reads A3's calibrated score if present (else raw).

## Tests

- [ ] **A** `build_labels` split is deterministic by seed; `label` derived from golden `expected_categories`; content-free (no values). Small golden fixture → `fit_calibrator` returns `PROVISIONAL` (< min_positives) with the right status enum.
- [ ] **B** `luhn`/`iban_mod97`/`aba_routing` pass on valid synthetic IDs, fail on off-by-one; `map_presidio_results` with a `validator` drops a checksum-fail match and emits `DETERMINISTIC_MATCH` on a pass (rule_id includes the validator).
- [ ] **C** review POST→GET round-trip; `review_events` gets an append per decision; export includes review columns; assert no source PII required and none leaks (SENSITIVE_TOKENS check); uncertainty sort orders lowest calibrated score first.
- [ ] **D** `preprocess_image` runs deterministically on a synthetic skewed+noisy image (bytes in→out, no exception); `PreprocessOcrProvider` with a fake rasterizer + fake ConvertClient returns concatenated OCR text for a PDF and an image; `build_ocr` selects it via `provider: preprocess`. Optional live test (skips without docling): gold-0012/0033 recover > 0 chars.

## Risks & Rollback

- **Calibration `PROVISIONAL` misread as failure** → surface the status explicitly on the eval page + README note; it's the correct §3.3 outcome for a small set. Rollback: leave `artefact: null` (reverts to `NOT_CALIBRATED`).
- **Checksum needs the matched value** → operate on the passed substring only, never log/persist it (same posture as reveal). Rollback: don't set `validator` (falls back to context-only classifier finding).
- **OCR preprocessing still can't read truly-destroyed scans** → then `unable_to_process/ocr_failure` remains, correctly (typed exception). New deps are `requirements-ml.txt`-only + lazy, so the base path/tests are unaffected. Rollback: `ocr.provider: docling` or `stub`.
- **Adjudication scope creep (Contract 5)** → keep to single-reviewer accept/reject/needs-info + audit; no dual-review/workflow engine. Rollback: feature is additive (separate store); disable the tab.
- **Warm-context cache** — B and D change the detection/OCR engines; `JobService.invalidate()` already exists → call it or restart after config changes.

## Review Notes

_(filled in after implementation / review)_
