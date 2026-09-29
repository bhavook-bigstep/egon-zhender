# ADR 0001 — WS-1 real engines and local-service deployment

- **Status:** accepted
- **Date:** 2026-09-29
- **Context:** WS-1 needs real extraction, OCR, detection, and LLM assessment. The
  RFP-baseline stack named native extractors · Tika · Docling · PaddleOCR · Presidio ·
  LLM (Qwen). During the PoC we fixed the concrete choices and their deployment shape.

## Decision

- **Extraction:** `NativeExtractor` (pypdf/python-docx/openpyxl) in-venv for born-digital
  PDF/DOCX/XLSX; **Docling** (docling-serve, container) as the extraction + OCR front door
  for scanned/rich-layout; **Tika** (container) for legacy `.doc/.xls`. All behind the
  `ExtractionEngine` port, config-selected (`decode | native | docling | tika`).
- **OCR:** the OCR gate runs a pluggable `OCRProvider`; the real backend reuses Docling
  (`HttpOcrProvider`). PaddleOCR PP-Structure remains an optional higher-fidelity backend.
- **Detection:** **Presidio** via `PresidioHttpEngine` (container) behind `DetectionEngine`
  (`regex | presidio | presidio_http`).
- **LLM:** external OpenAI-compatible API via `OpenWeightProvider` (config only); a LiteLLM
  proxy can front self-hosted or Bedrock later. Egress is approval-gated and minimised.
- **Deployment shape (Option A parity):** Docling/Presidio/Tika run as **local dedicated
  services** bound to loopback, images **pinned by digest**. Only the LLM may leave the
  boundary, and only with `is_local=false` + written approval + identifier hashing.

## Consequences

- Engine/service choices are config-driven and swappable; the skeleton (`decode`/`regex`/
  `mock`) stays the safe default. Reproducibility relies on pinned image digests + the
  `engines` block recorded in the run ledger + `detector_version` from config.
- Supersedes the RFP-baseline "PaddleOCR-first" reading of the stack table: Docling is the
  front door, a Paddle-family engine is an optional OCR backend. Root `CLAUDE.md` stack
  table updated accordingly.
- The "local, not egress" classification holds **only** while these services run on
  customer-controlled infra; the `InferenceConfig` boundary validator fails closed if
  `is_local` disagrees with a non-local URL.
