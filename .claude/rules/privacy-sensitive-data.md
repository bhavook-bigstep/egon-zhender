# Privacy & Sensitive-Data Rules

The corpus contains highly sensitive PII (financial, health, government-ID,
compensation, legal, confidential client information). Treat all content as PII.

## HARD BLOCKS (reject if violated)

1. **No sensitive content in logs, prints, errors, or docs** — Never write raw
   document/file-note text, evidence-span **text**, OCR output, or un-hashed
   identifiers (email/phone/LinkedIn) to a log, stdout, exception message, test
   snapshot, or solution doc. Reference items by **source ID** and evidence
   **location** only. (CLAUDE.md Contract 2.)
2. **No uncontrolled inference egress** — No data (content, snippets, prompts built
   from content, or identifiers) reaches a managed/external inference provider
   without **prior written approval**. Baseline inference is open-weight models on
   customer-controlled or dedicated infrastructure.
3. **Minimise before any hosted transfer** — Hash identifiers (email, phone,
   LinkedIn) with the Egon-Zehnder-held key before they leave the on-prem boundary.
   Never transfer more fields than the stage needs.
4. **No sensitive data in the repo** — No real records, samples, manifests with
   content, or truth sets containing PII are committed. Fixtures use synthetic data.

## REQUIRED PATTERNS

- **Evidence by location, not content:** findings cite where (item ID, page/sheet/
  cell/offset), never the sensitive string itself.
- **Redaction helper:** route anything user-facing/loggable through the shared
  redaction utility in `libs/`; do not build ad-hoc scrubbing per module.
- **Retention/TTL:** staged intermediate artefacts (extracted text, OCR output) get
  a TTL and are cleaned up; they are working data, not deliverables.
- **Least data:** the LLM/semantic stage receives the minimum span needed to assess,
  not the whole document, where the method allows.

## SUPPRESSIONS (do NOT flag)

- Synthetic fixtures with obviously fake data (`jane.doe@example.com`, `test-ssn`).
- Aggregate, non-identifying counts/metrics in logs (e.g. "312 items flagged").
