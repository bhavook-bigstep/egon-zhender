# Data Pipeline Rules (ingest · extract · OCR · detect · output)

## HARD BLOCKS (reject if violated)

1. **Frozen manifest per run** — Every run reads a frozen manifest of authorised
   source IDs with content hashes. Processing an item not in the manifest, or reading
   source without one, is a blocking failure. (Contract 4.)
2. **Read-only source** — Extraction/OCR never modifies a source file or record.
   Work on copies/streams; emit to a separate result set. (Contract 1.)
3. **Typed exceptions, never silent drops** — An item that cannot be processed
   (unsupported, unreadable, OCR failure, parser error) gets an explicit exception
   code on its output row. Items are never dropped without a trace.
4. **Every input yields exactly one output row** — Counts reconcile: input items ==
   output rows (flagged + not_flagged + unable_to_process). No row is lost or duplicated.

## REQUIRED PATTERNS

- **Stage ledger:** record per stage — item ID, stage outcome, OCR status/quality,
  parser exceptions — so a run reconciles end to end.
- **OCR gate:** run OCR only where the text layer is absent or fails quality checks
  (density, printable ratio, image coverage); record the gate decision and quality measure.
- **Preserve identifiers & metadata:** carry author, date/time, linked Executive,
  linked project (and source ID) through every stage to the output row.
- **Idempotent & resumable:** re-running on the same manifest + config produces the
  same result; a re-run can skip already-completed items via the ledger.
- **Config-driven:** taxonomy, recognisers, thresholds, and OCR settings come from
  versioned config, not literals.
- **Stream large inputs:** the document corpus is ~55 GB — stream/chunk; never load
  the whole corpus into memory (see `performance.md`).

## SUPPRESSIONS (do NOT flag)

- Synchronous, single-item processing inside a clearly-scoped debug/CLI script.
- In-memory handling of a single small item during its own processing.
