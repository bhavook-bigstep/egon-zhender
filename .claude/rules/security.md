# Security Rules

## HARD BLOCKS (reject if violated)

1. **No secrets in code, logs, or config committed to the repo** — Databricks
   tokens, cloud credentials, the identifier-hashing key, and model/API keys come
   from env or a secret manager. A committed secret is a breach that outlives the commit.
2. **Source access is read-only** — Open Databricks tables/volumes read-only. Never
   redact, delete, merge, create, or overwrite a Prince Houston or Zendai record.
   All outputs go to a separate result set. (RFP scope boundary; Contract 1.)
3. **No uncontrolled data egress** — No content, prompt-from-content, or identifier
   leaves the approved boundary except to customer-controlled/dedicated infrastructure,
   or to an external endpoint that has **prior written approval**. (Contract 2.)
4. **Never run active content** — Do not execute macros, embedded scripts, or active
   content in source documents during extraction. Parse inertly.
5. **No untrusted deserialization / query injection** — No `pickle` of untrusted
   input; parameterize any SQL against Databricks/DuckDB; validate file paths.

## REQUIRED PATTERNS

- **Least privilege:** access scoped to the specific tables/volumes the stage needs.
- **Key handling:** the hashing key is referenced, never stored in the repo; rotate
  per the engagement's key policy.
- **Deployment parity:** the same controls apply to Option A (on-prem) and Option B
  (dedicated AWS Frankfurt) — the boundary moves, the rules do not.
- **Retention/TTL** so staged sensitive intermediates do not accumulate.

## SUPPRESSIONS (do NOT flag)

- Test fixtures with obviously fake keys/tokens (e.g. `test-key-xxxx`).
- Read-only introspection queries against source schema for profiling.
