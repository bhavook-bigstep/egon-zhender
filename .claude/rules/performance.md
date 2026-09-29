# Performance Rules

Scale context: ~330k file notes + ~90k documents (~55 GB, up to ~1.4M pages,
~340k OCR pages) for WS1; ~88k people against a large Zendai snapshot for WS2.
For the **PoC**, correctness and explainability on the sample come first — but do
not choose an approach that cannot scale to these volumes in production.

## HARD BLOCKS (reject if violated)

1. **No loading the whole corpus into memory** — Stream/chunk documents and rows;
   process in bounded batches. Buffering 55 GB (or full OCR output) OOMs the worker.
2. **No unbounded, all-pairs matching** — WS2 must block/index before scoring. A full
   88k × Zendai cross-join is a non-starter. (See `matching-scoring.md`.)
3. **No N+1 source reads** — Batch Databricks/storage reads; do not fetch item-by-item
   in a tight loop when a batch read is available.

## REQUIRED PATTERNS

- **Bounded batches** with checkpointing to the run ledger so a run resumes, not restarts.
- **OCR only when gated** — OCR is the expensive stage; the gate keeps it off the
  ~95%+ of pages that already have a good text layer.
- **Bound concurrency** on OCR and LLM inference to the available CPU/GPU/memory.
- **Cache by content hash** where safe and privacy-preserving (skip re-extracting an
  unchanged item on re-run).
- **Set timeouts** on every external call (Databricks, OCR, model, Splink jobs).
- **Measure on the sample, extrapolate to full volume** — record throughput per stage
  in the PoC so production sizing is grounded, not guessed.

## SUPPRESSIONS (do NOT flag)

- Intentional single-item processing in admin/debug scripts.
- In-memory handling of one small item during its own processing step.
