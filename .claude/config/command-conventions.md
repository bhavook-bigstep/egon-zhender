# Command Conventions — Single Source of Truth

All commands read shared IDs, paths, and invariants from this file. Do not
hardcode these values across command files — reference this file instead.

## Data Locations (read-only source)

| Item                     | Location / Value          | Notes                                  |
| ------------------------ | ------------------------- | -------------------------------------- |
| Source corpus (WS1)      | Databricks tables/volumes | Read-only; frozen per run              |
| People records (WS2)     | Databricks (PH people)    | Read-only; ~88k Prince Houston people  |
| Zendai snapshot (WS2)    | Minimised snapshot        | Identifiers hashed before hosted use   |
| PoC sample               | `poc/` _(TBD)_            | Controlled sample for the PoC only     |
| Result set (outputs)     | `out/` _(TBD)_            | Separate from source; never overwrites |
| Run ledger               | `out/ledger/` _(TBD)_     | One ledger per run                     |
| Manifests                | `poc/manifests/` _(TBD)_  | Frozen authorised source IDs + hashes  |

## Configuration & Versions

> Fill these in as the PoC fixes them. Leave values empty until real.

| Item                          | ID / Value | Use                                    |
| ----------------------------- | ---------- | -------------------------------------- |
| Approved taxonomy version     | _(TBD)_    | WS1 sensitive-data categories          |
| WS1 LLM (baseline)            | Qwen (PoC-validated) | Contextual sensitive-data assessment |
| Inference endpoint            | _(TBD)_    | Customer-controlled / dedicated only   |
| Splink model / blocking rules | _(TBD)_    | WS2 probabilistic linkage              |
| Score thresholds / bands      | _(TBD)_    | Calibrated cut-offs per workstream     |
| Identifier hashing key ref    | _(TBD)_    | EZ-held key; never stored in repo      |

## Inference Egress Invariant

No data reaches a managed/external inference provider without **prior written
approval**. The baseline runs open-weight models on customer-controlled or
dedicated infrastructure. (See CLAUDE.md Contract 2.)

## Source Immutability Invariant

Never redact, delete, merge, create, or overwrite a Prince Houston or Zendai
record. Source is read-only; all results go to a separate result set. (RFP scope
boundary; CLAUDE.md Contract 1.)

## Sensitive-Data Invariant

Never log, echo, or post externally: sensitive content, evidence-span text, OCR
text, or un-hashed identifiers (email/phone/LinkedIn). Reference items by source
ID only. (See CLAUDE.md Contract 2.)

## Commit Safety Invariant

Never commit, push, or open a PR until the user has explicitly approved.
