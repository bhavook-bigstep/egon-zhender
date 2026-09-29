# Brainstorm: Golden dataset + evaluation & human-review loops

- **Date:** 2026-09-29
- **Prompt:** How to improve the PoC further (excluding the Databricks source connection and
  §3.4 output-format production) — pending tasks, other angles, and how such engagements
  are usually run.

## Problem Frame

```
Goal:        Move the WS-1 PoC from "runs end-to-end" to "provably accurate + reviewable":
             the measurement loop, the human loop, and the missing ground truth.
Workstream:  WS-1 (built) + shared eval/review tooling; WS-2 noted (unbuilt).
Inputs:      Rich synthetic corpus + config; a GOLDEN DATASET (to be built).
Sensitivity: All content PII — new surfaces stay metadata/location-first; reviewer content
             view stays gated; truth sets are synthetic.
Method:      Add eval/calibration + human review around the existing pipeline, on a golden set.
Output:      Precision/recall/calibration reports; adjudicated result set; golden dataset artifact.
Governance:  Contracts unchanged; everything reviewable + versioned + reproducible.
Constraints: PoC time-box; one taxonomy/sample/tuning cycle.
```
**In scope:** golden dataset, evaluation & calibration (A), human review (B).
**Out of scope (user):** Databricks source connection; §3.4 Delta/Parquet/Excel export.
**Out of PoC scope:** auth/RBAC, production scale-out, live-PII browsing.

## How engagements like this usually run
Profile → taxonomy → sample → detectors → **label ground truth** → **evaluate (P/R/F1)** →
**calibrate/tune** → **human clerical review of the uncertain band** → production → QA →
handover. We built the pipeline mechanics; the ground truth, the measurement loop, and the
human loop are missing — that is the gap this work closes.

## Prior Art
- **Internal:** `docs/solutions/patterns/ws1-web-ui-sse-sqlite-queue.md` (UI shell to extend
  for review); `matching-scoring.md` (calibration status, bands); the rich synthetic corpus
  `tests/fixtures/ws1_sample_rich/` (no truth labels yet); `Finding.review_status`/
  `Ws1Summary.calibration_status` already in the schema.
- **External:** see per-approach citations.

## Approaches (explored)

### Approach A — Evaluation & calibration harness  *(SELECTED)*
- **Idea:** golden truth set → per-category precision/recall/F1, reliability curve, and real
  score calibration (Platt/isotonic); CER/WER on the OCR items.
- **Fit:** synthetic truth (no real PII), reproducible, makes `calibration_status` real, boosts explainability.
- **Effort/Risk:** Medium / needs labels — solved by the golden dataset below.
- **Source:** Presidio evaluation framework — Microsoft — https://github.com/microsoft/presidio-research (accessed 2026-09-29) — sanctioned P/R + per-recognizer error analysis.
- **Source:** Probability calibration — scikit-learn — https://scikit-learn.org/stable/modules/calibration.html (accessed 2026-09-29) — sigmoid (Platt) vs isotonic, matching our config.
- **Source:** Character Error Rate — LlamaIndex — https://www.llamaindex.ai/glossary/what-is-character-error-rate (accessed 2026-09-29) — CER/WER for the extraction/OCR stage.

### Approach B — Human-in-the-loop review / adjudication  *(SELECTED)*
- **Idea:** reviewer works flagged/"possible" items (accept/reject/adjust), uncertainty-ordered
  (active learning), `review_status` persisted, exportable reviewed set.
- **Fit:** review status is metadata; matched content behind the gated reveal; auditable.
- **Effort/Risk:** Med-high / UI scope + reviewer PII (gated view).
- **Source:** What Is Human-in-the-Loop — IBM — https://www.ibm.com/think/topics/human-in-the-loop (accessed 2026-09-29) — HITL as the governance control on sensitive AI decisions.
- **Source:** Active Learning & HITL for NLP annotation — DZone — https://dzone.com/articles/active-learning-nlp-annotation (accessed 2026-09-29) — surface most-uncertain first (entropy/margin).

### Approach C — WS-2 (people matching) Splink skeleton  *(deferred — next)*
- **Source:** Splink: probabilistic record linkage at scale — Linacre et al. — https://www.researchgate.net/publication/363226193 (accessed 2026-09-29).

### Approach D — Method realism & perf hardening  *(deferred — opportunistic)*
- **Source:** OCR accuracy (CER/WER) — Docsumo — https://www.docsumo.com/blog/ocr-accuracy (accessed 2026-09-29); internal `.claude/rules/performance.md`.

## Decision — the golden dataset is the foundation

Both A and B need ground truth we don't have. Because the corpus is **synthetically
generated**, the generator knows every entity it plants — so it can **emit exact labels**
alongside the documents. Build a **golden dataset** as a tangible, versioned artifact:

- **Documents** (already generated) + **truth labels** per item: expected `flag_status`,
  expected `sensitivity_categories`, and per-entity ground truth (type, category, char
  span, and the planted value) — all deterministic from the seed.
- **Tangible + Databricks-ready:** stored as versioned files now (corpus + a `ws1_golden.*`
  truth table), in a schema that loads cleanly into Databricks later as **source + truth
  tables** (Databricks then becomes the read-only source — that connection stays out of
  this scope, but the schema is designed for it).
- **Reproducible:** fixed seed → identical bytes → stable hashes → stable `run_id`.

This golden set powers A (compare pipeline output vs truth → P/R/F1 + calibration) and B
(the review workflow operates on scored items, with truth available to score reviewers too).

## Comparison

| Approach | Effort | Risk | Source / AI-generated |
| -------- | ------ | ---- | --------------------- |
| Golden dataset (foundation) | Medium | Label schema must be Databricks-ready | Generator-emitted labels: **No source found — this is an AI-generated idea** (standard for synthetic data) |
| A — Eval & calibration | Medium | needs the golden set | Cited (Presidio eval, sklearn, CER/WER) |
| B — Human review | Med-high | UI scope, reviewer PII | Cited (IBM HITL, DZone AL) |
| C — WS-2 Splink | High | largest scope | Cited (Splink) — next |
| D — Realism/perf | Medium | infra heft | Cited (Docsumo) — opportunistic |

## Recommendation
Plan **golden dataset → A → B** as one arc (the dataset unblocks both). Defer C (WS-2) and
D. Next step: `/ph-poc:plan "golden dataset (synthetic, labelled, Databricks-ready) +
evaluation/calibration harness (A) + human review workflow (B)"`.
