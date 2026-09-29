# Testing Rules

## HARD BLOCKS (reject if violated)

1. **New logic ships with tests** — Any non-trivial function, pipeline stage,
   recogniser, or scoring rule needs a test. Untested code is a regression waiting
   to happen — and on this engagement a wrong result set is a client-facing failure.
2. **No tests on real PII** — Tests use **synthetic** fixtures only. Never assert on
   real records, real identifiers, real OCR output, or real model responses. Tests are
   deterministic and hermetic.
3. **No skipped / `.only` / xfail-without-reason tests committed** — They silently
   reduce coverage.

## REQUIRED PATTERNS

- **pytest** with fixtures for source items, manifests, and configs.
- **Mock the boundaries:** Databricks/storage client, OCR engine, and the LLM/model
  are mocked in unit tests. Keep a small set of integration tests that wire real stages
  over synthetic fixtures.
- **Cover the risk paths first:**
  - WS1: extraction/parser exceptions, OCR gate decisions, recogniser hits/misses,
    `unable_to_process` handling, one-row-per-input reconciliation.
  - WS2: deterministic key matches, blocking, rating thresholds, conflict detection,
    `Multiple`/`No match` edges.
- **Reproducibility test:** same manifest + config + seed produces identical output.
- **Redaction test:** assert logs/outputs never contain sensitive content or raw IDs.
- **Coverage target:** ~90% on changed lines; prioritise exception handling and
  scoring/threshold logic (highest risk).

## SUPPRESSIONS (do NOT flag)

- Generated code without hand-written logic.
- Thin pass-through adapters with no branching.
