# Plan: WS-1 Databricks source connector + full-dataset run → workbook + eval page

- **Date:** 2026-09-30
- **Author:** Claude
- **Status:** draft
- **Phase:** 1 of the "connector → output → review" arc (WS-2 out of scope; handled elsewhere)

## Intake Summary

```
Goal:        Make Databricks the read-only SOURCE: a DatabricksSourceReader reads the golden
             dataset (documents volume + manifest) from Unity Catalog; run WS-1 over the whole
             dataset from Databricks → the resultant workbook. Add an "expected vs actual"
             evaluation page comparing pipeline output to the golden ground truth.
Workstream:  WS-1 only. Shared source port + a new eval view.
Inputs:      UC volume /Volumes/workspace/prince_houston/ws1_golden/ (documents/ + manifest.jsonl
             + labels.jsonl); the existing engines (docling/presidio/semantic, Docker).
Sensitivity: Documents are PII (synthetic here). Reading FROM the customer's Databricks is IN
             boundary, not egress. Staged bytes are in-memory/TTL; eval surfaces are content-free
             (entity TYPES + categories + locations, never values unless the gated reveal).
Method:      Implement the SourceReader port against the Databricks SDK Files API; select via
             config (source.backend = databricks). Reuse the existing batch runner + workbook.
             Eval reads golden truth (manifest expected_* + labels) vs pipeline results.
Output:      A Databricks-sourced run populating the Workbook, plus an eval page with per-record
             expected-vs-actual + headline precision/recall/F1.
Governance:  Read-only source (port has no write); frozen manifest + content hashes; reproducible
             run_id; metadata/location-only surfaces; no content in logs.
Constraints: PoC time-box; one run/tuning cycle. PIPELINE RUNS LOCALLY reading Databricks as
             source/sink (NOT as a Databricks job — that is Option-A deployment, out of scope).
```

**Confirm at gate (assumption, PROBABLE):** the pipeline runs **locally** (our uvicorn/CLI +
local Docker engines) and reads Databricks as the source. A Databricks-*job* deployment is a
bigger Option-A piece and is out of this phase.

**In scope:** the connector, a Databricks config, the full-dataset run path, the eval page, tests.
**Out of scope:** production §3.4/§3.5 *output* back to Databricks (Phase 2); human review (Phase 3);
running the pipeline as a Databricks job; WS-2.

## Prior Learnings

- `libs/source/base.py` — the `SourceReader` port (`list_manifest`/`open_item`/`open_stream`)
  already anticipates this: *"Later a `DatabricksReader` implements the same protocol and drops
  in via config."* We follow the same **injectable-client + lazy-import** pattern used for the
  real engines (`docs/solutions/integrations/ws1-real-engines-http-adapters.md`).
- Critical patterns: #1 read-only (the port has no write); #2 no content in logs (reference by
  source ID; the reader logs metadata only); #3 egress — reading FROM the customer's Databricks
  is in-boundary, not off-boundary egress.
- The golden manifest already carries `expected_flag_status` + `expected_categories`, and
  `labels.jsonl` the per-entity truth — so the eval needs no new labelling.
- **Sources:**
  - Databricks SDK for Python — Databricks — https://docs.databricks.com/aws/en/dev-tools/sdk-python (accessed 2026-09-30): the sanctioned local SDK; auth via profile/OAuth/token.
  - `w.files` (Files API) — Databricks SDK for Python — https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html (accessed 2026-09-30): `w.files.download(path).contents.read()` for a UC volume file; stream to disk with `shutil.copyfileobj` to avoid loading large files into RAM.
  - Work with files in UC volumes — Databricks — https://docs.databricks.com/aws/en/volumes/volume-files (accessed 2026-09-30): volume URI form `/Volumes/<catalog>/<schema>/<volume>/<path>`.
  - Presidio evaluation (precision/recall/error analysis) — Microsoft — https://github.com/microsoft/presidio-research (accessed 2026-09-30): the metric approach the eval page reports (row/entity precision & recall).
  - The eval *page* form (expected-vs-actual UI in our admin) — **No source found — this is an AI-generated idea** (a straightforward comparison view over our own truth + results).

## Approach

**A DatabricksSourceReader implementing the existing port, selected by config.** It reads the
frozen manifest (`manifest.jsonl`) and each document's bytes from the UC volume via the
Databricks SDK Files API, using an **injectable `FilesClient`** (default = `WorkspaceClient().files`,
lazy-imported) so unit tests run against a fake with no workspace. `source.backend = databricks`
selects it; `source.root` is the volume base (`/Volumes/.../ws1_golden`), `source.manifest` the
relative manifest path, and item `path`s are volume-relative (mirrors the sample reader). No SQL
warehouse needed — the manifest + docs are files in the volume.

Running a **batch** on a Databricks-backed config processes the whole golden dataset from
Databricks; results land in the registry and the existing **Workbook** (latest-per-record) view.

The **eval page** (`/admin/eval`) loads the golden truth (`manifest.jsonl` expected_* +
`labels.jsonl`) and the latest results, and shows per record: expected vs actual `flag_status` +
categories (✓/✗), plus a headline **precision / recall / F1** for flagging and per category, and
a **scanned-vs-born-digital / by-severity** cut (using the manifest `scanned`/`scan_severity`).
Content-free: entity **types**/categories/counts and evidence **locations** only.

Key decisions (confidence):
- **SDK Files API over Spark/JDBC** (CERTAIN) — simplest local read; no cluster/warehouse; streams.
- **Injectable client + lazy import** (CERTAIN) — hermetic tests; `databricks-sdk` optional dep.
- **Manifest as a volume FILE, not a table read** (PROBABLE) — the manifest.jsonl is in the volume;
  reading it avoids a SQL warehouse. (A table-backed manifest can be added later.)
- **Eval reads truth from the same source location** (PROBABLE) — volume for databricks, local for sample.
- **Staged bytes are ephemeral** (CERTAIN) — process in-memory / stream; any temp gets a TTL cleanup.

**Contract check:** read-only (port has no write; SDK download only) ✓ · minimisation (log source
ID + metadata; eval shows types/locations, not values; reveal stays gated) ✓ · controlled inference
(unchanged) ✓ · explainable/scored (results unchanged; eval adds truth comparison) ✓ · reproducible
(frozen manifest + content hashes + deterministic run_id) ✓ · in-boundary (Databricks is the
customer source; local dev is synthetic) ✓.

## Tasks

| # | Task | Files | Depends on | Wave |
| - | ---- | ----- | ---------- | ---- |
| 1 | `SourceConfig`: add `profile: str | None` (databricks auth profile); keep `root`/`manifest` | `libs/schemas.py` | — | 1 |
| 2 | `DatabricksSourceReader` (port impl): `list_manifest` (download+parse manifest.jsonl), `open_item`, `open_stream`; injectable `files` client; lazy `databricks-sdk` import; log metadata only | `libs/source/databricks.py` | 1 | 1 |
| 3 | `build_reader`: select `DatabricksSourceReader` when `source.backend == "databricks"` | `pipelines/workstream1_sensitive/runner.py` | 2 | 1 |
| 4 | `databricks-sdk` optional dep (lazy) | `requirements.txt` (or `requirements-databricks.txt`) | — | 1 |
| 5 | `config/ws1.databricks.yaml` — backend=databricks, volume root/manifest, profile; docling/presidio_http/semantic; mock LLM | `config/ws1.databricks.yaml` | 1-3 | 2 |
| 6 | Golden truth loader — read manifest.jsonl expected_* + labels.jsonl (volume or local) → `{source_id: {expected_flag_status, expected_categories, entities}}` | `libs/eval/golden.py` | — | 3 |
| 7 | Eval metrics — per-record expected-vs-actual; precision/recall/F1 (flagging + per category); scanned/severity cut. Pure functions | `libs/eval/metrics.py` | 6 | 3 |
| 8 | Eval API + page — `GET /api/admin/eval` + `/admin/eval` (new admin tab); content-free comparison table + headline tiles | `app/main.py`, `app/templates/admin_eval.html`, `app/templates/_admin_header.html`, `app/static/app.js` | 6,7 | 3 |
| 9 | Tests — DatabricksSourceReader against a fake FilesClient (list/open/stream, read-only); golden loader + metrics (synthetic fixtures); eval API/page renders + no content leak | `tests/ws1/test_source_databricks.py`, `tests/ws1/test_eval.py`, `tests/app/test_pages.py` | 2,6,7,8 | 4 |
| 10 | Docs — WS-1 CLAUDE.md (databricks source + eval), README run note (`--config config/ws1.databricks.yaml`), the "runs locally reads Databricks" note | `pipelines/workstream1_sensitive/CLAUDE.md`, `README.md` | all | 4 |

Waves: **W1**={1,2,3,4}; **W2**={5}; **W3**={6,7,8}; **W4**={9,10}.

## Tests

Synthetic + hermetic (fake Databricks client; no workspace/PII). Real end-to-end run over
Databricks is validated by the user (I have no creds).

- [ ] `test_databricks_reader_list_manifest` — fake `files.download` returns a manifest.jsonl blob → parsed `ManifestEntry`s (extra golden fields ignored); order stable.
- [ ] `test_databricks_reader_open_item_stream` — `open_item`/`open_stream` download the right `root/path`; bytes match; streaming chunks reassemble.
- [ ] `test_databricks_reader_is_read_only` — the reader exposes no write; asserts only `download` is called.
- [ ] `test_golden_truth_loader` — parses expected_* + labels into the truth map.
- [ ] `test_eval_metrics` — known results vs known truth → expected precision/recall/F1 (flagging + per category); scanned cut counts.
- [ ] `test_eval_page_and_api` — `/admin/eval` renders the tab + table; `/api/admin/eval` returns metrics; no sensitive tokens (content-free).

## Risks & Rollback

- **No workspace creds here** → I build + fake-test; you validate the real Databricks run. The
  connector is behind the port/config, so nothing else changes if it's swapped out.
- **SDK auth/version drift** → reader takes an injectable client; auth via the same profile/OAuth
  you configured for the CLI (`DATABRICKS_CONFIG_PROFILE` / host+token).
- **Large-file memory** → `open_stream` uses chunked download (`copyfileobj`); the batch already streams.
- **Truth/label drift** → truth loaded from the same golden artifact that produced the manifest;
  keyed on value+type for entities (offset-independent).
- **Rollback:** additive — new reader + config + eval page; delete `libs/source/databricks.py`,
  `config/ws1.databricks.yaml`, and the eval files to revert. No source data touched.

## Review Notes
_(filled in after implementation / review)_
