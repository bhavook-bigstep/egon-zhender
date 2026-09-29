# Plan: <Title>

- **Date:** YYYY-MM-DD
- **Author:** <name / Claude>
- **Status:** draft | approved | done

## Intake Summary

```
Goal:        [One sentence]
Workstream:  [WS1 sensitive-data / WS2 matching / shared libs]
Inputs:      [Databricks tables/volumes, formats, PoC sample scope]
Sensitivity: [taxonomy categories touched; PII / financial / health / gov-ID / etc.]
Method:      [deterministic rules / OCR / semantic screen / LLM / Splink]
Output:      [row fields produced; explainability + score/band]
Governance:  [manifest, config version, run ledger, reproducibility]
Constraints: [read-only source, no external inference w/o approval, minimisation, PoC time-box]
```

## Prior Learnings

- Relevant `docs/solutions/` entries, critical patterns, and `docs/requirement/`
  constraints found (or "none"). Sources for any novel decision (citation or
  "no source found — AI-generated").

## Approach

Describe the chosen approach. For non-trivial work, list the alternatives
considered and why this one wins. Note contract implications (read-only source,
sensitive-data minimisation, controlled inference, explainable + scored output,
reproducibility). Confirm it stays within PoC scope.

Tag key decisions: (CERTAIN / PROBABLE / UNCLEAR).

## Tasks

| # | Task | Files | Depends on | Parallel? |
| - | ---- | ----- | ---------- | --------- |
| 1 |      |       | —          | yes/no    |

## Tests

- [ ] Test case 1 (what it proves) — synthetic fixture
- [ ] Test case 2

## Risks & Rollback

- Risk → mitigation.
- How to roll back if it goes wrong.

## Review Notes

_(filled in after implementation / review)_
