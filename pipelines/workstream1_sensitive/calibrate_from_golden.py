"""Fit a WS-1 calibration artefact from a completed run's findings + the golden truth.

    python -m pipelines.workstream1_sensitive.calibrate_from_golden \
        --findings poc/out-databricks/batch-<id>/ws1_findings.jsonl \
        --out config/ws1_calibration.json --method sigmoid

Content-free: uses finding SCORES + golden CATEGORY labels only (never any matched value).
`sigmoid`/`isotonic` need scikit-learn (requirements-ml.txt); `identity` needs no ML dep.
The §3.3 rule (≥min-positives labelled positives AND holdout error ≤ max) decides
CALIBRATED vs PROVISIONAL vs NOT_CALIBRATED per category — applied inside `fit_calibrator`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from libs.calibration import fit_calibrator
from libs.eval.calibration_labels import build_labels
from libs.eval.golden import DEFAULT_GOLDEN_DIR, load_golden_truth


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fit a WS-1 calibration artefact from a run's findings + golden truth."
    )
    parser.add_argument("--findings", required=True, help="ws1_findings.jsonl from a run")
    parser.add_argument(
        "--golden-dir", default=os.environ.get("WS1_GOLDEN_DIR", str(DEFAULT_GOLDEN_DIR))
    )
    parser.add_argument("--out", default="config/ws1_calibration.json")
    parser.add_argument("--method", default="sigmoid")  # identity | sigmoid | isotonic
    parser.add_argument("--version", default="cal-golden-0")
    parser.add_argument("--holdout-frac", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--min-positives", type=int, default=100)
    parser.add_argument("--max-holdout-error", type=float, default=5.0)
    args = parser.parse_args()

    findings = [
        json.loads(line)
        for line in Path(args.findings).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    truth = load_golden_truth(args.golden_dir)
    labels = build_labels(
        findings, truth, holdout_frac=args.holdout_frac, seed=args.seed
    )
    calibrator = fit_calibrator(
        labels,
        version=args.version,
        method=args.method,
        min_positives=args.min_positives,
        max_holdout_error=args.max_holdout_error,
    )
    Path(args.out).write_text(
        json.dumps(calibrator.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    counts = {
        category: len(splits.get("dev", [])) + len(splits.get("holdout", []))
        for category, splits in labels.items()
    }
    print(f"wrote {args.out} (version={calibrator.version}); pairs/category: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
