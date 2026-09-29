# Plan: WS-1 Phase 2 — Deepen the Detect → Assess → Score Core

- **Date:** 2026-09-28
- **Author:** Claude
- **Status:** done

## Intake Summary

```
Goal:        Swap the skeleton stubs for real detection (Presidio), semantic + LLM
             assessment (embeddings + open-weight provider), and calibration —
             behind the ports already in place. Prove the WS-1 METHOD on the sample.
Workstream:  WS-1 detect/assess/score + libs/inference real adapter + libs/calibration.
Inputs:      Same versioned synthetic sample (tests/fixtures/ws1_sample) + a small
             SYNTHETIC labelled dev/holdout truth set for calibration.
Sensitivity: Synthetic only; PII rules still apply (minimal span to the model;
             evidence by location; no content in logs).
Method:      detect → Presidio (checksum/context deterministic + NER probabilistic);
             assess → semantic embedding screen (SIMILARITY, routes what reaches the
             model) + LLM classification via InferenceProvider (open-weight adapter,
             structured output, approval-gated); score → calibration_status logic.
Output:      Same row schema; findings now carry real scores + calibration status.
Governance:  Versioned recogniser set + model version + calibration artefact version
             + run ledger; deterministic given fixed versions + greedy decoding.
Constraints: Read-only source; controlled inference (local default, managed approval-
             gated, is_local-derived); minimisation; explainable+scored; reproducible;
             PoC time-box (one tuning cycle).
```

**PoC scope:** yes. **No real LLM/GPU in this dev env** — the open-weight adapter is
built and validated against a mock/fake; a real endpoint plugs in via config when
available. Heavy engines (Presidio, SBERT, sklearn) are **lazy-imported behind
factories**, so the existing stub path (`engine: regex`, `provider: mock`) still runs
with the light dependency set and the test suite stays hermetic.

## Prior Learnings

- `docs/solutions/INDEX.md` — empty. Critical patterns 2 & 3 (content-in-logs, inference
  egress) are the load-bearing constraints for the LLM path.
- Deferred notes in `pipelines/workstream1_sensitive/CLAUDE.md` — this plan closes the
  **egress fail-safe** (derive `crosses_boundary` from the provider) and **span-limit →
  config** items; port-parity (OCR/audit) stays deferred.
- Response §3.3 (internal) — the calibration rule this plan implements verbatim:
  `CALIBRATED` only where a category has ≥100 labelled positives **and** blind-holdout
  calibration error ≤5 points; else `PROVISIONAL`; `NOT_CALIBRATED` where no data;
  `NOT_APPLICABLE` for deterministic. Score types: DETERMINISTIC_MATCH / SIMILARITY /
  MODEL_SCORE / CLASSIFIER_SCORE (already in `libs/schemas.py`).
- **Sources for novel decisions:**
  - Presidio custom recognisers (checksum + context) — Microsoft —
    https://microsoft.github.io/presidio/analyzer/adding_recognizers/ (accessed 2026-09-28):
    PatternRecognizer + validation (checksum) + context words; deterministic vs NER split.
  - Semantic screen — Sentence Transformers, Semantic Textual Similarity — sbert.net —
    https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html
    (accessed 2026-09-28): embed + cosine similarity to per-category examples for routing.
  - Calibration — scikit-learn, Probability calibration (sigmoid/Platt + isotonic,
    CalibratedClassifierCV) — https://scikit-learn.org/stable/modules/calibration.html
    (accessed 2026-09-28): the two mappings + OvR for multi-class + CV to avoid bias.
  - LLM structured output — vLLM Structured Outputs — https://docs.vllm.ai/en/latest/features/structured_outputs/
    (accessed 2026-09-28): `guided_choice`/JSON-schema constrained decoding for reliable
    classification labels (prevents malformed/hallucinated output).
  - Open-weight serving behind one interface — vLLM OpenAI-Compatible Server
    (https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) + LiteLLM
    (https://github.com/BerriAI/litellm) (accessed 2026-09-28): drop-in OpenAI-format
    endpoint the `OpenWeightProvider` targets.

## Approach

Deepen each stage **behind its existing interface**, selected by config, so stub and
real coexist and tests stay hermetic by injecting fakes for the three heavy engines
(analyzer, embedder, LLM client). Key decisions tagged.

**1. Detection engine (CERTAIN).** Introduce `DetectionEngine` protocol
(`analyze(text, source_id) -> list[Finding]`) with two impls chosen by
`detect.engine`: `RegexEngine` (today's logic, behaviour-preserving) and
`PresidioEngine` (lazy-imports `presidio_analyzer`). Presidio results map to `Finding`
via config: `deterministic_entities` (checksum/validated, e.g. CREDIT_CARD/Luhn) →
`DETERMINISTIC_MATCH` + `rule_id`, no score; other (NER/context) entities →
`CLASSIFIER_SCORE` with `score = presidio_confidence*100` + band + calibration status.
`category_map` maps entity types → taxonomy categories. One custom checksum+context
recogniser included as the pattern for future ones.

**2. Semantic screen (PROBABLE).** `TextEmbedder` protocol (`embed(texts)->vectors`)
with `SbertEmbedder` (lazy `sentence_transformers`). `SemanticScreen` embeds the item
span, cosine-compares to configured per-category example embeddings, emits `SIMILARITY`
findings (routing/prioritisation only — not a probability), and **routes**: only
categories scoring above `route_threshold` are sent to the LLM. This minimises egress
(fewer/smaller model calls) — a data-minimisation win, not just cost.

**3. LLM provider (CERTAIN interface / PROBABLE endpoint).** `OpenWeightProvider`
implements `InferenceProvider` against an OpenAI-compatible `base_url`
(lazy `httpx`/`openai`), using structured output (`guided_choice` over the taxonomy
labels) + greedy decoding (temperature 0) for reproducibility, returning a
`MODEL_SCORE` (from logprobs where exposed, else agreement across constrained passes).
Add `is_local` to the provider; `assess.py` sets `crosses_boundary = not provider.is_local`
(**closes the egress fail-safe P3**); managed endpoints still require `approval_written`.

**4. Calibration (CERTAIN).** `libs/calibration.py`: fit a per-category mapping
(sigmoid/Platt or isotonic via sklearn) from the labelled dev set, evaluate calibration
error on the blind holdout, and assign `calibration_status` per the §3.3 rule. A
`calibrate.py` tool builds a **versioned artefact** (`config/ws1_calibration.json`);
the runner applies it to `MODEL_SCORE`/`CLASSIFIER_SCORE` findings (deterministic stays
`NOT_APPLICABLE`). On the tiny synthetic set the honest result is `PROVISIONAL`/
`NOT_CALIBRATED` — which correctly proves the mechanism, not a fake “calibrated”.

**Reproducibility (PROBABLE).** Greedy decoding + fixed model/recogniser/calibration
versions recorded in the ledger; embeddings are deterministic. Residual LLM
nondeterminism is exactly why the holdout/calibration exists; versions are pinned in
config and asserted in the ledger.

**Contract check:** read-only (unchanged) ✓ · controlled inference (local default;
managed approval-gated; `is_local`-derived crossing) ✓ · minimisation (semantic routing
+ minimal span) ✓ · explainable (SIMILARITY/MODEL_SCORE/CLASSIFIER_SCORE + band +
calibration_status; deterministic cites rule_id) ✓ · reproducible (versioned artefacts +
ledger + greedy) ✓ · PoC scope (one tuning cycle; extraction/OCR + surrounding parts
still deferred) ✓.

## Tasks

| # | Task | Files | Depends on | Parallel? |
| - | ---- | ----- | ---------- | --------- |
| 1 | Provider `is_local` + derive `crosses_boundary` from provider (closes egress P3) | `libs/inference/base.py`, `libs/inference/mock.py`, `pipelines/workstream1_sensitive/assess.py` | — | no (foundation) |
| 2 | `DetectionEngine` protocol + factory; refactor regex logic into `RegexEngine` (no behaviour change) | `pipelines/workstream1_sensitive/detect.py`, `.../detect_regex.py` | 1 | yes |
| 3 | `PresidioEngine` (lazy) + entity→category/deterministic mapping + 1 custom checksum/context recogniser | `.../detect_presidio.py`, `libs/schemas.py` (DetectConfig fields) | 2 | no |
| 4 | `TextEmbedder` protocol + `SbertEmbedder` (lazy) + `SemanticScreen` (SIMILARITY + routing) | `.../semantic.py`, `libs/schemas.py` (assess.semantic cfg) | 1 | yes |
| 5 | `OpenWeightProvider` (OpenAI-compatible, structured output, logprobs→score, `is_local`) | `libs/inference/openweight.py` | 1 | yes |
| 6 | `assess.py` orchestration: semantic route → LLM on routed categories; emit SIMILARITY + MODEL_SCORE | `.../assess.py` | 4,5 | no |
| 7 | `libs/calibration.py` (fit/apply + §3.3 status) + `calibrate.py` artefact builder; runner applies it | `libs/calibration.py`, `.../calibrate.py`, `.../runner.py`, `.../score.py` | 1 | yes |
| 8 | Config schema + `config/ws1.yaml` Phase 2 keys + `config/ws1_calibration.json` | `libs/schemas.py`, `config/ws1.yaml` | 3,4,5,7 | no |
| 9 | Synthetic labelled dev/holdout fixtures for calibration | `tests/fixtures/build_ws1_sample.py`, `tests/fixtures/ws1_calibration_labels.json` | 7 | yes |
| 10 | `requirements-ml.txt` (presidio-analyzer, spaCy model, sentence-transformers, scikit-learn, httpx) + install notes | `requirements-ml.txt`, `README.md` | — | yes (early) |
| 11 | Tests (fakes for analyzer/embedder/LLM; calibration status; egress; mapping) | `tests/ws1/*` | 3,6,7 | partly |
| 12 | Docs: update root `CLAUDE.md` stack table (mark Presidio/SBERT/Qwen/calibration PoC-validated), WS1 CLAUDE.md deepen notes | `CLAUDE.md`, `pipelines/workstream1_sensitive/CLAUDE.md` | 6,7 | no |

Parallel waves: **W1**={1,10}; **W2**={2,4,5,7}; **W3**={3,6}; **W4**={8,9}; **W5**={11,12}.

## Tests

Synthetic + hermetic; the three heavy engines are injected as fakes (no network, no
model download). Real-engine paths get one optional integration test each, skipped if
the import/model is absent.

- [ ] `test_detect_presidio_mapping` — fake analyzer returns a checksum entity → `DETERMINISTIC_MATCH`+rule_id (no score); an NER entity → `CLASSIFIER_SCORE` with score+band; correct category_map.
- [ ] `test_detect_engine_factory` — `engine: regex` vs `presidio` selects the right impl; unknown → ValueError.
- [ ] `test_semantic_screen_routing` — fake embedder: category above `route_threshold` is routed to the LLM and emits a SIMILARITY finding; below is not.
- [ ] `test_openweight_provider` — fake HTTP client: request carries the minimal span + `guided_choice` labels + greedy params; canned response parsed → `MODEL_SCORE`; `is_local=False` + no approval → `InferenceEgressError`.
- [ ] `test_assess_egress_flag_from_provider` — `crosses_boundary` derived from `provider.is_local` (mock local → False; openweight managed → True).
- [ ] `test_calibration_status` — synthetic arrays: ≥100 positives & holdout error ≤5 → `CALIBRATED`; 50 positives → `PROVISIONAL`; 0 → `NOT_CALIBRATED`; deterministic → `NOT_APPLICABLE`.
- [ ] `test_calibration_apply` — mapping transforms a raw score and stamps the status on the finding; deterministic findings untouched.
- [ ] `test_reproducibility_phase2` — same sample + config + calibration artefact → identical output (with fake engines).
- [ ] `test_end_to_end_phase2` — full run with fakes matches an updated truth set; reconciliation still balances; ledger records recogniser/model/calibration versions.
- [ ] Regression: existing 41 tests still pass (regex/mock path unchanged).

## Risks & Rollback

- **Heavy deps / no GPU** → engines lazy-imported behind factories; base install + tests
  stay light; real engines optional. Rollback = keep `engine: regex`, `provider: mock`.
- **LLM nondeterminism** → greedy decoding + structured output + pinned model_version;
  calibration on a blind holdout; versions asserted in the ledger.
- **Over-fitting calibration on a tiny synthetic set** → the §3.3 gate makes it honestly
  report `PROVISIONAL`/`NOT_CALIBRATED`; we prove the mechanism, not a number.
- **Scope creep** → extraction/OCR robustness and the surrounding-parts order remain out
  of this plan (separate slices).
- **Rollback:** all new files + additive config; revert by deleting the Phase 2 modules
  and resetting `config/ws1.yaml` selectors to `regex`/`mock`. No source data touched.

## Review Notes

**Implemented 2026-09-28.** All 12 tasks landed behind the existing ports, config-selected,
heavy engines lazy-imported. Gates: ruff ✓, mypy ✓ (31 files), pytest ✓ **67 passed + 2
skipped** (the optional real-engine integration tests skip without `requirements-ml.txt`).
The default skeleton path (regex/mock/no-calibration) is unchanged — same run_id + reconcile.

Delivered: `DetectionEngine` factory + `RegexEngine`/`PresidioEngine`; `SemanticScreen`
(SBERT) + routing; `OpenWeightProvider` (OpenAI-compatible, structured output) with
`is_local`-derived egress (closes the egress fail-safe P3); `libs/calibration.py`
(sigmoid/isotonic/identity + §3.3 status) + `calibrate.py` tool + synthetic labels;
`finalize_scored` applies calibration + band centrally; SIMILARITY findings recorded but
excluded from flagging. Not yet exercised on real data (no LLM/GPU in this env) — real
engines validated against fakes; endpoint plugs in via config.

Still deferred (recorded in WS1 CLAUDE.md): OCR/audit port parity, `_MAX_SPAN_CHARS` +
MODEL/CLASSIFIER `threshold_version` → config, production streamed output writes.
