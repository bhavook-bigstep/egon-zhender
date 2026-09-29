"""Build a versioned calibration artefact from a labelled dev/holdout set.

    python -m pipelines.workstream1_sensitive.calibrate \
        --labels tests/fixtures/ws1_calibration_labels.json \
        --out config/ws1_calibration.json --method identity

`identity` needs no ML dependency; `sigmoid`/`isotonic` require `requirements-ml.txt`.
Labels are SYNTHETIC (testing rules). The artefact is JSON so the runtime applies it
without any ML dependency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from libs.calibration import fit_calibrator


def _load_labels(
    path: Path,
) -> dict[str, dict[str, list[tuple[float, int]]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        category: {
            split: [(float(score), int(label)) for score, label in rows]
            for split, rows in splits.items()
        }
        for category, splits in raw.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit a WS-1 calibration artefact.")
    parser.add_argument("--labels", default="tests/fixtures/ws1_calibration_labels.json")
    parser.add_argument("--out", default="config/ws1_calibration.json")
    parser.add_argument("--method", default="identity")  # identity | sigmoid | isotonic
    parser.add_argument("--version", default="cal-0")
    parser.add_argument("--min-positives", type=int, default=100)
    parser.add_argument("--max-holdout-error", type=float, default=5.0)
    args = parser.parse_args()

    labels = _load_labels(Path(args.labels))
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
    print(f"wrote {args.out} (version={calibrator.version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
