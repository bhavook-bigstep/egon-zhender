"""Build calibration labels from a completed WS-1 run against the golden truth.

Turns a run's `ws1_findings.jsonl` rows plus the golden ground truth into the
`{category: {"dev": [...], "holdout": [...]}}` structure that `libs.calibration.
fit_calibrator` consumes. Content-free: only the numeric score and a binary
correct/incorrect label survive — never the matched string or any identifier.

Only scored findings participate (CLASSIFIER_SCORE / MODEL_SCORE, where `score`
is not None). Deterministic findings carry a rule ID and no score, so they are
skipped here rather than fed a fabricated probability (Contract 3 / matching-
scoring rule 2). The dev/holdout split is deterministic given the same inputs and
seed (Contract 4).
"""

from __future__ import annotations

import random

from libs.eval.golden import GoldenTruth


def build_labels(
    findings: list[dict],
    truth: dict[str, GoldenTruth],
    *,
    holdout_frac: float = 0.4,
    seed: int = 1729,
) -> dict[str, dict[str, list[tuple[float, int]]]]:
    """Group scored findings into per-category dev/holdout (value, label) splits.

    A finding contributes a pair only when its ``score`` is not None (i.e. it is a
    probabilistic/AI score) and its ``source_id`` is present in ``truth``. The label
    is 1 when the finding's category is one the golden truth expects for that record,
    else 0. Within each category the pairs are sorted by ``(value, label)`` for a
    stable order, shuffled with ``random.Random(seed)``, and the last
    ``round(holdout_frac * n)`` become the blind holdout, the rest the dev set.
    Categories with no pairs are omitted.
    """
    by_category: dict[str, list[tuple[float, int]]] = {}
    for finding in findings:
        score = finding.get("score")
        if score is None:
            continue
        source_id = finding["source_id"]
        record = truth.get(source_id)
        if record is None:
            continue
        category = finding["category"]
        label = 1 if category in record.expected_categories else 0
        by_category.setdefault(category, []).append((float(score), label))

    labels: dict[str, dict[str, list[tuple[float, int]]]] = {}
    for category, pairs in by_category.items():
        ordered = sorted(pairs, key=lambda pair: (pair[0], pair[1]))
        random.Random(seed).shuffle(ordered)
        n_holdout = round(holdout_frac * len(ordered))
        dev = ordered[: len(ordered) - n_holdout]
        holdout = ordered[len(ordered) - n_holdout :] if n_holdout else []
        labels[category] = {"dev": dev, "holdout": holdout}
    return labels
