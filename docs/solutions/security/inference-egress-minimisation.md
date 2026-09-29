---
title: Inference egress needs minimisation + boundary validation, not just an approval gate
category: security
date: 2026-09-29
status: solved
tags: [ws1, contract-2, egress, minimisation, hashing, privacy]
---

## Problem

Wiring the external (managed) LLM added an off-boundary egress path. The pipeline had an
approval gate (`ensure_egress_allowed`: `crosses_boundary and not approval_written`), which
felt sufficient — but a privacy review found two independent holes that the gate did not
cover.

## Investigation path

- Privacy review traced the managed-LLM path: `assess()` sent the raw 512-char span
  straight into the request. The span can contain un-hashed identifiers (email/phone/
  LinkedIn). Contract 2 requires **hashing identifiers with the EZ key before *any* hosted
  transfer** — a control *independent* of the approval gate. It did not exist.
- Second hole: `crosses_boundary` was derived solely from a hand-set `is_local` flag. A
  one-line misconfig (`is_local: true` + a remote `base_url`) would send spans off-boundary
  while the gate stayed silent — bypass by misconfiguration, not fail-safe by construction.

## Root cause

Treating "written approval" as the whole of Contract 2. Egress control is three things,
each of which must **fail closed**: (1) approval, (2) data minimisation before transfer,
(3) a boundary decision that can't be silently mis-set.

## Solution (key files)

- `libs/minimisation.py` — `mask_identifiers()` replaces email/phone/LinkedIn with keyed
  HMAC pseudonyms (`libs/hashing.hash_identifier`, EZ key from env); `load_key()` raises
  `MinimisationKeyError` if the key is absent (fail closed).
- `pipelines/workstream1_sensitive/assess.py` — masks the span whenever
  `not provider.is_local`, before building the `InferenceRequest`; raw span only on the
  local path.
- `libs/schemas.py` — `InferenceConfig` `model_validator` rejects `is_local: true` with a
  non-local `base_url` (`_is_local_host`), so the boundary flag can't disagree with the
  destination.
- Committed default stays `provider: mock` / `is_local: true` → nothing egresses unless a
  human turns it on.

## Prevention / reuse

- Any new hosted-transfer path must run through **both** the approval gate **and**
  identifier minimisation, and derive/validate the boundary from the **destination host**,
  not a free-standing flag. All three fail closed.
- Never log request bodies or service responses; reference items by source ID + evidence
  location only. See also [[ws1-real-engines-http-adapters]].
