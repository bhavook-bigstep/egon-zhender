"""retag_truth: re-derive golden truth for the current taxonomy (synthetic, hermetic)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

# Load the migration script by path (it lives under datasets/, not an importable package).
_SPEC = importlib.util.spec_from_file_location(
    "retag_truth", Path("datasets/ws1_golden/retag_truth.py")
)
assert _SPEC and _SPEC.loader
retag_truth = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(retag_truth)


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _manifest(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        out[row["source_id"]] = row
    return out


def _lbl(sid: str, entity: str, cat: str, in_tax: bool) -> dict:
    return {"source_id": sid, "entity_type": entity, "category": cat, "in_taxonomy": in_tax}


def _rec(sid: str, flag: str, cats: list[str]) -> dict:
    return {
        "source_id": sid,
        "content_hash": f"h-{sid}",
        "expected_flag_status": flag,
        "expected_categories": cats,
    }


def test_retag_promotes_contact_and_recomputes_expectations(tmp_path: Path) -> None:
    _write(tmp_path / "labels.jsonl", [
        _lbl("g-0", "email", "out_of_taxonomy", False),  # email only (was out-of-taxonomy)
        _lbl("g-1", "swift_bic", "financial", True),  # financial + a phone
        _lbl("g-1", "phone_number", "out_of_taxonomy", False),
        _lbl("g-2", "first_name", "out_of_taxonomy", False),  # non-promoted PII
    ])
    _write(tmp_path / "manifest.jsonl", [
        _rec("g-0", "not_flagged", []),
        _rec("g-1", "flagged", ["financial"]),
        _rec("g-2", "not_flagged", []),
    ])

    changed = retag_truth.retag(tmp_path)
    manifest = _manifest(tmp_path / "manifest.jsonl")
    labels = [json.loads(line) for line in (tmp_path / "labels.jsonl").read_text().splitlines()]

    # g-0: email-only → now flagged, contact_identifier
    assert manifest["g-0"]["expected_flag_status"] == "flagged"
    assert manifest["g-0"]["expected_categories"] == ["contact_identifier"]
    # g-1: keeps financial, gains contact_identifier (from the phone)
    assert manifest["g-1"]["expected_categories"] == ["contact_identifier", "financial"]
    # g-2: a non-promoted out-of-taxonomy entity stays not_flagged
    assert manifest["g-2"]["expected_flag_status"] == "not_flagged"
    assert manifest["g-2"]["expected_categories"] == []
    # labels: the email/phone rows were promoted; content hashes untouched
    promoted = [r for r in labels if r["entity_type"] in ("email", "phone_number")]
    assert promoted
    assert all(r["category"] == "contact_identifier" and r["in_taxonomy"] for r in promoted)
    assert manifest["g-0"]["content_hash"] == "h-g-0"  # documents/hashes never change
    assert changed == 2  # g-0 (flag flip) and g-1 (category added)

    # idempotent — a second run changes nothing
    assert retag_truth.retag(tmp_path) == 0
