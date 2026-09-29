# WS-1 Golden Dataset

A tangible, **labelled**, multi-format corpus for evaluating and reviewing Workstream 1.
Fully **synthetic** (see `NOTICE.md`) — safe to commit and to load into Databricks as the
read-only source + ground-truth tables.

Regenerate (deterministic): `python datasets/ws1_golden/build_golden_dataset.py`

## Contents

```
documents/<source_id>.<ext>   rendered files: .txt .pdf .png .docx .xlsx
manifest.jsonl                one row per document  (→ Databricks "documents"/source table)
labels.jsonl                  one row per entity    (→ Databricks "labels"/truth table)
NOTICE.md                     attribution (Nemotron-PII, CC BY 4.0)
```

## Mixture (realistic positive/negative mix)

- **flagged** — contains in-taxonomy PII (financial / government_id / health)
- **not_flagged (has PII)** — only out-of-taxonomy PII (name / email / phone / …)
- **not_flagged (clean)** — no PII at all (generated)

Formats span **born-digital** (text layer) and **scanned** (image-only / degraded → OCR):

- Born-digital: `.txt`, `.pdf` (text layer), `.docx`, `.xlsx`, `.png` (clean render)
- Scanned (OCR path): `.pdf` image-only (no text layer) and `.jpg` degraded scans —
  skew, blur, contrast loss, sensor noise, JPEG artefacts, at `light` / `medium` / `heavy`
  severity. Heavy scans intentionally stress the OCR gate and may yield low-quality or
  `unable_to_process` results — that is deliberate coverage for the extraction/OCR eval.

## Schemas

**manifest.jsonl** (source table)

| field | meaning |
| ----- | ------- |
| `source_id` | stable id, e.g. `gold-0007` |
| `content_type` | MIME type |
| `content_hash` | sha256 of the file bytes |
| `path` | file path relative to this dir |
| `scanned` | true for image-only/degraded docs (OCR path) |
| `scan_severity` | `light`/`medium`/`heavy` for scanned docs, else null |
| `expected_flag_status` | `flagged` / `not_flagged` (ground truth) |
| `expected_categories` | in-taxonomy categories present (ground truth) |
| `has_pii` | any PII at all (incl. out-of-taxonomy) |
| `source_dataset` | `nvidia/Nemotron-PII` or `generated-clean` |
| `source_uid`, `domain`, `document_type`, `document_format`, `locale` | provenance/metadata |

**labels.jsonl** (truth table) — one row per ground-truth entity

| field | meaning |
| ----- | ------- |
| `source_id` | document it belongs to |
| `entity_type` | upstream label (e.g. `ssn`, `credit_debit_card`, `email`) |
| `category` | our taxonomy (`financial`/`government_id`/`health`) or `out_of_taxonomy` |
| `in_taxonomy` | whether it is one of the three flagged categories |
| `value` | the matched string (synthetic) |

## How it's used

- **Evaluation (A):** run WS-1 over `documents/`, compare output to `labels.jsonl`
  (match on entity value + type/category — robust to PDF/OCR reformatting) → precision /
  recall / F1 per category + calibration.
- **Review (B):** the reviewer works the scored items; `labels.jsonl` grades decisions.
- **Databricks (later):** load `manifest.jsonl` + `labels.jsonl` as two tables and point
  the source reader at the `documents/` volume — the schema is already table-shaped.
