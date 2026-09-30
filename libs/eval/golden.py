"""Golden-truth loader for the WS-1 evaluation.

Reads the golden dataset's ground truth — `manifest.jsonl` (expected flag/categories +
scan metadata) and `labels.jsonl` (per-entity truth) — into a per-record map. The golden
files are versioned locally (`datasets/ws1_golden/`); the same content is the Databricks
copy, so evaluation works regardless of which backend a run sourced from.

Content note: `value` (the matched string) is present in labels but is NOT loaded here —
the evaluation compares entity TYPES/categories only (content-free).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GOLDEN_DIR = Path("datasets/ws1_golden")


@dataclass(frozen=True)
class GoldenEntity:
    entity_type: str
    category: str
    in_taxonomy: bool


@dataclass(frozen=True)
class GoldenTruth:
    source_id: str
    expected_flag_status: str
    expected_categories: tuple[str, ...]
    scanned: bool
    scan_severity: str | None
    entities: tuple[GoldenEntity, ...] = field(default_factory=tuple)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_golden_truth(golden_dir: str | Path = DEFAULT_GOLDEN_DIR) -> dict[str, GoldenTruth]:
    """Return {source_id: GoldenTruth} from the golden manifest + labels."""
    root = Path(golden_dir)
    entities: dict[str, list[GoldenEntity]] = {}
    for row in _read_jsonl(root / "labels.jsonl"):
        entities.setdefault(row["source_id"], []).append(
            GoldenEntity(
                entity_type=row.get("entity_type", ""),
                category=row.get("category", ""),
                in_taxonomy=bool(row.get("in_taxonomy")),
            )
        )
    truth: dict[str, GoldenTruth] = {}
    for row in _read_jsonl(root / "manifest.jsonl"):
        source_id = row["source_id"]
        truth[source_id] = GoldenTruth(
            source_id=source_id,
            expected_flag_status=row.get("expected_flag_status", "not_flagged"),
            expected_categories=tuple(row.get("expected_categories", []) or []),
            scanned=bool(row.get("scanned")),
            scan_severity=row.get("scan_severity"),
            entities=tuple(entities.get(source_id, [])),
        )
    return truth
