# Code Review Checklist

## Verdict System

Every review ends with exactly one verdict:

- **APPROVED** — No blocking issues; safe to merge.
- **APPROVED_WITH_COMMENTS** — Mergeable; non-blocking suggestions noted.
- **CHANGES_REQUIRED** — At least one blocker; must be fixed before merge.

## Priority Classification

| Priority | Meaning                                                          |
| -------- | --------------------------------------------------------------- |
| **P1**   | Blocker — source mutation, PII/content leak, uncontrolled egress, unexplained output, non-reproducible run, broken build |
| **P2**   | Should fix — correctness/scoring/perf issue, weak test          |
| **P3**   | Nice to have — style, naming, minor cleanup                      |

## Blocker Finding Format

```
### [P1] <Short title>
**File:** path/to/file:line
**Category:** privacy | source-immutability | explainability | reproducibility | security | correctness | performance | testing
**Issue:** What is wrong and what it causes.
**Fix:** Specific change (with code where useful).
```

## 8-Area Checklist

1. **Correctness** — Does it do what the plan/spec says? Edge cases (unreadable items, ties, empty candidates) handled?
2. **Source immutability** — Source opened read-only; no write/redact/merge/overwrite of any record; outputs to a separate result set.
3. **Privacy (PII)** — No sensitive content, evidence text, OCR text, or raw identifiers in logs/outputs/tests; minimisation + hashing before hosted transfer.
4. **Inference boundary** — No data to external/managed inference without written approval; open-weight on controlled infra by default.
5. **Explainability** — Every output row has reason + evidence location + score type (deterministic vs AI/probabilistic) + band/calibration where applicable.
6. **Reproducibility** — Frozen manifest + versioned config + run ledger; deterministic; counts reconcile (one row per input).
7. **Tests** — New logic covered; exception paths and scoring/threshold logic tested; synthetic fixtures; deterministic.
8. **Performance** — Streaming/batching; OCR gated; WS2 blocked (no all-pairs); timeouts set.

If clean: state "No blocking issues found" and the verdict.
