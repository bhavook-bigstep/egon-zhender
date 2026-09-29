# Brainstorm: WS-1 First — Walking Skeleton, then Harden the Surroundings

- **Date:** 2026-09-28
- **Prompt:** Complete the WS-1 workflow first and prove it once; then build the
  surrounding parts in order — Audit, then multiple LLM providers, then the input bin
  (real source access).

## Problem Frame

INTAKE SUMMARY

```
Goal:        Build and PROVE the WS-1 sensitive-data workflow end-to-end first;
             then harden the surrounding parts in order — Audit, then multi-LLM
             provider, then the input bin (real source access).
Workstream:  WS-1 (sensitive-data identification). WS-2 untouched this round.
Inputs:      Our own SAMPLE TEST ENV (synthetic notes/docs) behind a stub source —
             no client data during the build.
Sensitivity: Synthetic-only now; pipeline obeys the PII rules from day one
             (evidence by location, no content in logs).
Method:      ingest -> extract -> OCR-gate -> detect (Presidio) -> assess
             (semantic + LLM) -> score/band -> one output row.
Output:      WS-1 rows (status·category·reason·evidence-location·score/band·exception),
             reconciling one row per input.
Governance:  Thin manifest + versioned config + a minimal ledger from the start.
Constraints: Read-only source; controlled inference; explainable+scored; reproducible;
             PoC time-box. Keep the seams for Audit/LLM/Source so later hardening is drop-in.
```

- **In scope:** WS-1 workflow + the *thin* stubs of the three surrounding parts needed
  to run it.
- **Out of scope (this round):** WS-2; production-grade Audit; multi-provider LLM
  routing; Databricks source connector — deferred to the "respective orders" after WS-1
  is proven. Out of PoC scope entirely: production scale-out.
- **Ordering nuance:** WS-1 cannot run with nothing underneath it, so "WS-1 first" means
  building it against **minimal stubs** (local sample bin + single/mock LLM + bare
  ledger), proving it, then thickening **Audit -> multi-LLM -> input bin** in that order.
  The rule that makes the sequence cheap: **put the seams in as interfaces (ports) from
  day one** so each later part drops in without reworking WS-1.

## Prior Art

- **Internal:** WS-1 sequence and stage libraries are fixed in
  `pipelines/workstream1_sensitive/CLAUDE.md:14-24`; decision rules
  (FLAGGED / NOT_FLAGGED / UNABLE_TO_PROCESS) and score types in our response §3.2-3.3;
  `docs/solutions/INDEX.md` empty. Library choices are settled — this brainstorm is
  about **build sequence**, not re-picking tools.
- **External:** see per-approach citations.

## Approaches

### Approach A — Walking skeleton (thin vertical slice) behind ports — RECOMMENDED
- **Idea:** Build the whole WS-1 chain *thin* end-to-end on the sample env first:
  smallest real version of each stage, with Source / LLM / Audit as **stub adapters
  behind interfaces (ports)**. Prove one-row-per-item, reconciliation, and the
  explainability wiring before deepening any stage; then thicken stages and swap stubs
  for real adapters in the stated order.
- **Fit with contracts:** every contract is exercised on day one (read-only stub,
  controlled-inference stub, explainable rows, reproducible run) cheaply, on synthetic data.
- **Effort / Risk:** Med / can feel featureless early.
- **Source:** Start with a Walking Skeleton — 97 Things Every Software Architect Should
  Know (O'Reilly) — https://www.oreilly.com/library/view/97-things-every/9780596800611/ch60.html
  (accessed 2026-09-28): thinnest end-to-end slice linking all major components so
  architecture and features evolve together. Hexagonal Architecture (Ports & Adapters) —
  https://bitloops.com/resources/software-architecture/hexagonal-architecture
  (accessed 2026-09-28): swap stub/real adapters for the same port without touching core
  logic — the seam strategy.

### Approach B — Stage-depth-first
- **Idea:** Build each stage fully (extraction, then OCR, then detect…) before assembling
  end-to-end.
- **Fit with contracts:** each stage is production-quality sooner, but reconciliation /
  one-row-per-input aren't proven until integration.
- **Effort / Risk:** Med-High / late integration surprises.
- **Source:** **No source found — this is an AI-generated idea** (the conventional
  big-bang integration anti-pattern the walking-skeleton literature argues against).

### Approach C — Detection-core-first (risk / method-first)
- **Idea:** Build Detect + Assess + Score/Band against *pre-supplied synthetic extracted
  text*, deferring extract/OCR plumbing. The PoC's real question is accuracy /
  explainability / calibration — not "can we read a PDF."
- **Fit with contracts:** front-loads the method proof the PoC is judged on; extraction /
  OCR are known-solved plumbing.
- **Effort / Risk:** Low-Med to first signal / seam mismatch if the text+metadata
  contract is loose (mitigated by defining it up front).
- **Source:** response §3.3 & §7 make method accuracy/calibration the acceptance
  criterion (`docs/requirement/EZ_PH_DC_2026_01_Agentics_Response.docx`). Presidio —
  Adding recognizers — https://microsoft.github.io/presidio/analyzer/adding_recognizers/
  (accessed 2026-09-28): the detect core can be built and tested independently of extraction.

## Comparison

| Approach | Effort | Risk | Source / AI-generated |
| -------- | ------ | ---- | --------------------- |
| A — Walking skeleton + ports | Med | Feels featureless early | Cited (97 Things, Hexagonal) |
| B — Stage-depth-first | Med-High | Late integration surprises | AI-generated |
| C — Detection-core-first | Low-Med | Seam mismatch if contract loose | Cited (response §3.3/§7, Presidio) |

## Recommendation

**Approach A, sequenced with C's priority.** Lay the walking skeleton (locks seams,
reconciliation, explainable-row shape on the sample env), then thicken the
Detect -> Assess -> Score core first (that proves the method), then extraction/OCR
robustness. With ports already in place, the stated follow-on order —
**Audit -> multi-LLM -> input bin** — becomes drop-in adapter swaps, not WS-1 rework.
Best fit for the time-box: an end-to-end demoable plus the method proof early, no
big-bang integration.

**Next step:** `/ph-poc:plan` on Approach A — scope: define ports for Source/LLM/Audit ->
thin WS-1 skeleton on sample env -> deepen detect/assess/score -> then the
surrounding-parts order (Audit, multi-LLM, input bin).
