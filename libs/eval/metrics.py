"""Expected-vs-actual evaluation metrics for WS-1.

Compares pipeline results (latest row per record) against the golden truth: flagging
precision/recall/F1, per-category precision/recall, a scanned-vs-born-digital recall cut,
and per-record rows for the UI. Pure functions — content-free (flag status, categories,
scan metadata only). Synthetic truth only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from libs.eval.golden import GoldenTruth


def _pr(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def evaluate(
    results: list[dict[str, Any]],
    truth: dict[str, GoldenTruth],
    categories: Sequence[str],
) -> dict[str, Any]:
    """Score results (each: source_id, flag_status, sensitivity_categories) vs truth.

    `categories` is the run's versioned taxonomy (`cfg.taxonomy.categories`) — never a
    literal here, so the per-category breakdown always tracks the approved taxonomy.

    A record whose pipeline outcome is `unable_to_process` is a processing FAILURE, not a
    content determination: it is excluded from the flagging confusion matrix, the
    per-category counts, and the scanned recall buckets, and counted separately as
    `unable_to_process`. Its per-record row carries `flag_match=None` so the reviewer sees
    a distinct state rather than a fabricated ✓/✗.
    """
    taxonomy = tuple(categories)
    by_id = {r["source_id"]: r for r in results}

    flag: Counter[str] = Counter()  # tp/fp/fn/tn for flagged-vs-not
    cat_counts: dict[str, Counter[str]] = {c: Counter() for c in taxonomy}
    scan_recall: dict[str, Counter[str]] = {
        "scanned": Counter(),
        "born_digital": Counter(),
    }
    rows: list[dict[str, Any]] = []
    evaluated = 0
    unable = 0

    for source_id in sorted(truth):
        gt = truth[source_id]
        result = by_id.get(source_id)
        if result is None:
            continue  # not processed yet — skip from metrics
        actual_flag = result.get("flag_status", "not_flagged")

        # A processing failure is not a determination — surface it, never score it.
        if actual_flag == "unable_to_process":
            unable += 1
            rows.append(
                {
                    "source_id": source_id,
                    "expected_flag_status": gt.expected_flag_status,
                    "actual_flag_status": actual_flag,
                    "flag_match": None,
                    "expected_categories": sorted(set(gt.expected_categories)),
                    "actual_categories": [],
                    "categories_match": None,
                    "scanned": gt.scanned,
                    "scan_severity": gt.scan_severity,
                }
            )
            continue

        evaluated += 1

        expected_flagged = gt.expected_flag_status == "flagged"
        actual_flagged = actual_flag == "flagged"
        if expected_flagged and actual_flagged:
            flag["tp"] += 1
        elif not expected_flagged and actual_flagged:
            flag["fp"] += 1
        elif expected_flagged and not actual_flagged:
            flag["fn"] += 1
        else:
            flag["tn"] += 1

        # scanned-vs-born-digital flagging recall (only where a flag is expected)
        if expected_flagged:
            bucket = "scanned" if gt.scanned else "born_digital"
            scan_recall[bucket]["expected"] += 1
            if actual_flagged:
                scan_recall[bucket]["found"] += 1

        # per-category (expected categories vs actual)
        expected_cats = set(gt.expected_categories)
        actual_cats = set(result.get("sensitivity_categories") or [])
        for cat in taxonomy:
            in_exp, in_act = cat in expected_cats, cat in actual_cats
            if in_exp and in_act:
                cat_counts[cat]["tp"] += 1
            elif in_act and not in_exp:
                cat_counts[cat]["fp"] += 1
            elif in_exp and not in_act:
                cat_counts[cat]["fn"] += 1

        rows.append(
            {
                "source_id": source_id,
                "expected_flag_status": gt.expected_flag_status,
                "actual_flag_status": actual_flag,
                "flag_match": expected_flagged == actual_flagged,
                "expected_categories": sorted(expected_cats),
                "actual_categories": sorted(actual_cats),
                "categories_match": expected_cats == actual_cats,
                "scanned": gt.scanned,
                "scan_severity": gt.scan_severity,
            }
        )

    by_scanned = {
        bucket: {
            "expected": counts.get("expected", 0),
            "found": counts.get("found", 0),
            "recall": round(counts.get("found", 0) / counts["expected"], 3)
            if counts.get("expected")
            else 0.0,
        }
        for bucket, counts in scan_recall.items()
    }

    return {
        "categories": list(taxonomy),
        "counts": {
            "truth_records": len(truth),
            "evaluated": evaluated,
            "unable_to_process": unable,
            "flag_tp": flag["tp"],
            "flag_fp": flag["fp"],
            "flag_fn": flag["fn"],
            "flag_tn": flag["tn"],
        },
        "flagging": _pr(flag["tp"], flag["fp"], flag["fn"]),
        "by_category": {
            cat: {
                **_pr(c["tp"], c["fp"], c["fn"]),
                "tp": c["tp"], "fp": c["fp"], "fn": c["fn"],
            }
            for cat, c in cat_counts.items()
        },
        "by_scanned": by_scanned,
        "rows": rows,
    }
