"""Re-derive the golden TRUTH columns in place for the current taxonomy.

When the approved taxonomy changes (here: `contact_identifier` added for email/phone),
the ground truth must follow or the evaluation penalises correct detections. This
recomputes, from `labels.jsonl`:

  * each label's `category` / `in_taxonomy` for the promoted entity types, and
  * each record's `expected_categories` / `expected_flag_status` in `manifest.jsonl`.

Documents and content hashes are NOT touched, so already-processed results stay valid and
no re-run is needed. Idempotent. Keep `PROMOTED` in sync with build_golden_dataset.py's
`_CATEGORY_MAP`. Run from the repo root:  python datasets/ws1_golden/retag_truth.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path("datasets/ws1_golden")

# Entity types promoted into the taxonomy beyond the original 3-category build.
PROMOTED = {"email": "contact_identifier", "phone_number": "contact_identifier"}


def _read(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def retag(out: Path = OUT) -> int:
    """Re-derive truth columns in `out`; return the number of manifest rows changed."""
    labels = _read(out / "labels.jsonl")
    for row in labels:  # re-categorise the promoted entity types
        promoted = PROMOTED.get(row.get("entity_type", ""))
        if promoted is not None:
            row["category"] = promoted
            row["in_taxonomy"] = True

    # expected categories/flag per record = the in-taxonomy categories present in its labels
    expected: dict[str, set[str]] = {}
    for row in labels:
        if row.get("in_taxonomy"):
            expected.setdefault(row["source_id"], set()).add(row["category"])

    manifest = _read(out / "manifest.jsonl")
    changed = 0
    for rec in manifest:
        cats = sorted(expected.get(rec["source_id"], set()))
        flag = "flagged" if cats else "not_flagged"
        if rec.get("expected_categories") != cats or rec.get("expected_flag_status") != flag:
            changed += 1
        rec["expected_categories"] = cats
        rec["expected_flag_status"] = flag

    manifest.sort(key=lambda r: r["source_id"])
    labels.sort(key=lambda r: (r["source_id"], r["entity_type"]))
    (out / "manifest.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in manifest), encoding="utf-8"
    )
    (out / "labels.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in labels), encoding="utf-8"
    )
    print(f"retagged {len(labels)} labels; updated {changed}/{len(manifest)} manifest rows")
    return changed


if __name__ == "__main__":
    retag()
