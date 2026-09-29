# Workstream 2 — People-Record Matching — CLAUDE.md

Inherits: root `CLAUDE.md` (contracts, anti-patterns), `.claude/rules/matching-scoring.md`,
`.claude/rules/privacy-sensitive-data.md`, `.claude/rules/data-pipeline.md`,
`.claude/rules/security.md`, `.claude/rules/performance.md`, `.claude/rules/testing.md`.

## Purpose

Compare ~88,000 Prince Houston people against a minimised Zendai snapshot and emit
one explainable, rated output row per person. Records are read-only; matching never
merges, creates, or overwrites a record — Egon Zehnder decides on the ratings.

## Method

```
1 Normalise    Standardise names, emails, phones, employers, dates; hash identifiers before any hosted transfer
2 Deterministic Exact keys (hashed email / phone / LinkedIn, strong composite keys) → Confirmed candidates
3 Blocking      Multi-rule blocking to bound comparisons (no all-pairs cross-join)
4 Probabilistic Splink (Fellegi-Sunter) scoring on blocked pairs; record model version
5 Conflict rules Surface conflicting attributes (employer, DOB, location) rather than hide them
6 Rate & output Map to Confirmed / High / Possible / Multiple / No match via configured thresholds
```

## Required Output Fields (per RFP + response)

Source person ID · rating (`Confirmed / High / Possible / Multiple / No match`) ·
numeric confidence · candidate Zendai IDs · matched attributes · conflicting
attributes · review status.

## WHY Deterministic + Splink

- **Deterministic keys first** give high-precision, explainable `Confirmed` matches
  with no scoring ambiguity (root Contract 3).
- **Blocking before scoring** keeps 88k × large-Zendai tractable — an all-pairs
  comparison is a non-starter (performance rules).
- **Splink / Fellegi-Sunter** gives calibratable probabilistic scores for the
  ambiguous remainder, with a model version recorded for reproducibility (Contract 4).
- **Identifier hashing** (email/phone/LinkedIn) enforces data minimisation before any
  hosted transfer (Contract 2).

## Key Files and Locations (once scaffolded)

| Component        | Location            | Description                                 |
| ---------------- | ------------------- | ------------------------------------------- |
| Normalisation    | `normalise/`        | Standardise + hash identifiers              |
| Deterministic    | `deterministic/`    | Exact/composite key matching                |
| Blocking + Splink| `linkage/`          | Blocking rules + Fellegi-Sunter model       |
| Conflict + rating| `rating/`           | Conflict rules + threshold → rating mapping |
| Output/ledger    | `output/`           | Row assembly + run ledger + reconciliation  |

## Testing

pytest with **synthetic** fixtures. Cover deterministic key matches, blocking
correctness, rating threshold boundaries, conflict detection, and `Multiple` /
`No match` edges. Mock the Zendai snapshot; never assert on real records. Assert
identifiers are hashed before any simulated hosted transfer.
