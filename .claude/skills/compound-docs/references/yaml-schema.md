# Solution Doc Frontmatter Schema

Every `docs/solutions/<category>/<slug>.md` starts with YAML frontmatter that
validates against this schema.

## Required Fields

| Field      | Type            | Rule                                                                       |
| ---------- | --------------- | -------------------------------------------------------------------------- |
| `title`    | string          | Short, specific. Not "bug fix".                                            |
| `category` | enum            | One of: `bugs` · `patterns` · `integrations` · `performance` · `security` · `matching` |
| `severity` | enum            | One of: `low` · `medium` · `high` · `critical`                             |
| `date`     | string          | `YYYY-MM-DD` (the date solved).                                            |
| `tags`     | array of string | 2–5 tags, lowercase, kebab-case.                                          |

## Optional Fields

| Field     | Type            | Rule                                             |
| --------- | --------------- | ------------------------------------------------ |
| `related` | array of string | Paths to related solution docs.                  |
| `pr`      | string          | PR number/URL where the fix landed.              |

## Example

```yaml
---
title: OCR gate misfires on born-digital PDFs with a thin text layer
category: performance
severity: high
date: 2026-10-02
tags: [ocr, gating, pdf, throughput]
related: []
pr: ""
---
```
