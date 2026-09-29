# Matching & Scoring Rules (detection scores · Splink linkage · calibration)

Applies to WS1 sensitivity scoring and WS2 people-record matching — anywhere a
score, band, or rating is produced.

## HARD BLOCKS (reject if violated)

1. **Every output row is explainable** — A flag or match with no reason and no score
   type is a blocking failure. WS1 rows carry category + reason + evidence location +
   score type; WS2 rows carry rating + numeric confidence + matched/conflicting
   attributes + candidate IDs. (Contract 3.)
2. **Distinguish deterministic from probabilistic/AI** — Deterministic (rule/checksum/
   exact-key) findings are labelled as such and cite the rule ID. AI/probabilistic
   findings carry a numeric score, a band, and a calibration status. Never present a
   scored guess as a deterministic fact.
3. **No magic-number thresholds in code** — Score cut-offs, bands, and Splink blocking
   rules live in versioned config, not inline literals. A threshold change is a config
   change, reviewable and reproducible.
4. **No fabricated confidence** — A score must come from the model/linkage output, not
   an invented constant to make a row look decided.

## REQUIRED PATTERNS

- **WS2 ratings:** map linkage output to `Confirmed / High / Possible / Multiple /
  No match` via configured thresholds; `Multiple` when several candidates tie.
- **Splink:** use deterministic keys first, then blocking rules to bound comparisons,
  then Fellegi-Sunter probabilistic scoring; record the model version. Conflicting
  attributes (e.g. mismatched employer/DOB) are surfaced, not hidden.
- **Calibration:** where labelled truth-set data exists, calibrate scores and record
  calibration status per finding; where it does not, mark the score uncalibrated.
- **Bands over false precision:** report a band (with the raw score available), not a
  spurious 6-decimal probability, in business-readable output.
- **Truth sets are synthetic in fixtures:** never commit real labelled PII.

## SUPPRESSIONS (do NOT flag)

- A documented default threshold in config awaiting PoC calibration (labelled as such).
- Deterministic rules with no score (correct — they carry a rule ID instead).
