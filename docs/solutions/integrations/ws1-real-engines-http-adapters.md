---
title: WS-1 real engines behind ports via Docker (Docling/Presidio/Tika)
category: integrations
date: 2026-09-29
status: solved
tags: [ws1, docling, presidio, tika, ports-and-adapters, docker, reproducibility]
---

## Problem

WS-1 needed real extraction / OCR / detection (and an external LLM) without bloating the
venv, breaking the hermetic test suite, or the deterministic skeleton path. Heavy engines
(Docling, Presidio, Tika, PaddleOCR, an LLM) can't all be pip-installed here (no GPU, no
Java), and a naive integration would couple pipeline stages to specific engines and make
runs non-reproducible.

## Investigation path

- Probed the environment first: `pip --dry-run` (native libs OK), `java -version` (absent →
  Tika must be a service), `docker` (available). This decided *what runs where* before any
  code.
- Chose containers for heavy engines + in-venv for light native extractors, all behind the
  existing `ExtractionEngine` / `DetectionEngine` / `OCRProvider` / `InferenceProvider`
  ports, config-selected.
- **Verified each service's live API against the running container, not the docs.**
  Docling's documented `file_sources`/top-level `to_formats` was wrong; the real body is
  `{sources:[{kind:"file",base64_string,filename}], options:{to_formats:["text"]}}`
  (found via `/openapi.json`). Presidio `/analyze` returns `{entity_type,start,end,score}`;
  Tika is `PUT /tika`.
- A six-agent review then caught reproducibility + egress gaps (see Prevention).

## Root cause / key decisions

- Heavy deps belong in **containers**, reached via thin HTTP adapters with an **injectable
  client** so unit tests use fakes (hermetic) and optional live tests skip when a container
  is down. Native (pypdf/python-docx/openpyxl) stays in-venv.
- Engines are **lazy-imported inside the factory branch**; the skeleton path
  (`decode`/`regex`/`mock`) needs none of it and stays the committed default.

## Solution (key files)

- Ports/factories: `pipelines/workstream1_sensitive/extract_engine.py`, `detect.py`,
  `ocr_gate.py` (`OCRProvider`), `libs/inference/*`.
- Adapters: `extract_native.py`, `extract_docling.py` (+ shared `build_convert_payload`),
  `extract_tika.py`, `detect_presidio_http.py`, `ocr_http.py`.
- Every adapter: `except PipelineItemError: raise` then `except Exception as exc: raise
  PipelineItemError(<CODE>, ...) from exc` — typed, fail-loud, one row per item.
- `docker-compose.yml` (images **pinned by digest**, ports bound to `127.0.0.1`),
  `config/ws1.docker.yaml`. Decision recorded in `docs/adr/0001-ws1-engines-and-local-services.md`.

## Prevention / reuse

- New engine? Add a Protocol adapter with an injectable client, a fake-client unit test
  (success / empty / transport-error → typed code / factory + missing-URL), and an
  optional live test that skips when unreachable. Verify the live API before trusting docs.
- **Pin image digests** and record engine/model versions in the run ledger — `:latest`
  breaks Contract 4 reproducibility. Bind service ports to loopback (unauthenticated
  services receiving document bytes).
- Watch for host **port clashes** (3000 was taken → Presidio host port moved to 3001).
- See also [[inference-egress-minimisation]].
