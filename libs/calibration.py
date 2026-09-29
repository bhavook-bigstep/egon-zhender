"""Score calibration (Contract 3 / response §3.3).

Fits a per-category mapping from raw scores to probabilities and assigns a
`calibration_status`:

- CALIBRATED    — category has >= min_positives labelled positives AND blind-holdout
                  calibration error <= max_holdout_error (points).
- PROVISIONAL   — some labelled data, but below that bar.
- NOT_CALIBRATED — no suitable data (score is a ranking only).

`apply` and the status rule are pure Python (hermetic, no sklearn). Only the sigmoid /
isotonic curve fitting lazy-imports scikit-learn; the `identity` method is pure Python
and used to exercise the status logic in tests. Artefacts are JSON so the runtime
applies a calibration without any ML dependency.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from libs.schemas import CalibrationStatus


@dataclass
class CategoryCalibration:
    status: CalibrationStatus
    method: str = "identity"  # identity | sigmoid | isotonic
    a: float | None = None  # sigmoid params: p = 1 / (1 + exp(a*s + b))
    b: float | None = None
    x: list[float] = field(default_factory=list)  # isotonic knots (score in 0-1)
    y: list[float] = field(default_factory=list)  # isotonic knots (prob in 0-1)

    def map_score(self, raw_0_100: float) -> float:
        """Map a raw 0-100 score to a calibrated 0-100 score."""
        s = max(0.0, min(1.0, raw_0_100 / 100.0))
        if self.method == "sigmoid" and self.a is not None and self.b is not None:
            import math

            prob = 1.0 / (1.0 + math.exp(self.a * s + self.b))
        elif self.method == "isotonic" and self.x and self.y:
            prob = _interp(s, self.x, self.y)
        else:  # identity
            prob = s
        return max(0.0, min(100.0, prob * 100.0))


def _interp(value: float, xs: list[float], ys: list[float]) -> float:
    if value <= xs[0]:
        return ys[0]
    if value >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if value <= xs[i]:
            span = xs[i] - xs[i - 1]
            if span == 0:
                return ys[i]
            frac = (value - xs[i - 1]) / span
            return ys[i - 1] + frac * (ys[i] - ys[i - 1])
    return ys[-1]


class Calibrator:
    def __init__(
        self, version: str, per_category: dict[str, CategoryCalibration]
    ) -> None:
        self.version = version
        self._per_category = per_category

    @classmethod
    def empty(cls) -> Calibrator:
        return cls(version="cal-none", per_category={})

    @classmethod
    def load(cls, path: str | Path) -> Calibrator:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        per = {
            category: CategoryCalibration(
                status=CalibrationStatus(entry["status"]),
                method=entry.get("method", "identity"),
                a=entry.get("a"),
                b=entry.get("b"),
                x=entry.get("x", []),
                y=entry.get("y", []),
            )
            for category, entry in data.get("categories", {}).items()
        }
        return cls(version=data.get("version", "cal-none"), per_category=per)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "categories": {
                category: {k: v for k, v in asdict(cal).items() if v not in (None, [])}
                | {"status": cal.status.value}
                for category, cal in sorted(self._per_category.items())
            },
        }

    def apply(self, category: str, raw_score: float) -> tuple[float, CalibrationStatus]:
        cal = self._per_category.get(category)
        if cal is None:
            return raw_score, CalibrationStatus.NOT_CALIBRATED
        if cal.status in (CalibrationStatus.CALIBRATED, CalibrationStatus.PROVISIONAL):
            return cal.map_score(raw_score), cal.status
        return raw_score, cal.status


def calibration_error(cal: CategoryCalibration, holdout: list[tuple[float, int]]) -> float:
    """Expected calibration error over the holdout, in points (0-100)."""
    if not holdout:
        return 100.0
    bins: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for raw, label in holdout:
        prob = cal.map_score(raw) / 100.0
        index = min(9, int(prob * 10))
        bins[index].append((prob, label))
    total = len(holdout)
    error = 0.0
    for bucket in bins:
        if not bucket:
            continue
        avg_pred = sum(p for p, _ in bucket) / len(bucket)
        avg_true = sum(y for _, y in bucket) / len(bucket)
        error += (len(bucket) / total) * abs(avg_pred - avg_true)
    return error * 100.0


def _fit_curve(
    method: str, dev: list[tuple[float, int]]
) -> CategoryCalibration:
    if method == "identity":
        return CategoryCalibration(status=CalibrationStatus.PROVISIONAL, method="identity")
    # sigmoid / isotonic use scikit-learn (lazy import; fitting is a tool-time step).
    import numpy as np

    scores = np.array([[raw / 100.0] for raw, _ in dev])
    labels = np.array([label for _, label in dev])
    if method == "sigmoid":
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression().fit(scores, labels)
        coef = float(model.coef_[0][0])
        intercept = float(model.intercept_[0])
        # p = sigmoid(coef*s + intercept) = 1/(1+exp(-(coef*s+intercept)))
        return CategoryCalibration(
            status=CalibrationStatus.PROVISIONAL,
            method="sigmoid",
            a=-coef,
            b=-intercept,
        )
    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        iso = IsotonicRegression(out_of_bounds="clip").fit(
            scores.ravel(), labels.astype(float)
        )
        xs = sorted({float(v) for v in scores.ravel()})
        ys = [float(iso.predict([x])[0]) for x in xs]
        return CategoryCalibration(
            status=CalibrationStatus.PROVISIONAL, method="isotonic", x=xs, y=ys
        )
    raise ValueError(f"unsupported calibration method: {method}")


def fit_calibrator(
    labels_by_category: dict[str, dict[str, list[tuple[float, int]]]],
    version: str,
    method: str = "sigmoid",
    min_positives: int = 100,
    max_holdout_error: float = 5.0,
) -> Calibrator:
    """Fit per-category calibrations and assign statuses per the §3.3 rule."""
    per: dict[str, CategoryCalibration] = {}
    for category, splits in labels_by_category.items():
        dev = splits.get("dev", [])
        holdout = splits.get("holdout", [])
        positives = sum(1 for _, label in dev if label == 1)
        if positives == 0:
            per[category] = CategoryCalibration(status=CalibrationStatus.NOT_CALIBRATED)
            continue
        cal = _fit_curve(method, dev)
        error = calibration_error(cal, holdout)
        if positives >= min_positives and error <= max_holdout_error:
            cal.status = CalibrationStatus.CALIBRATED
        else:
            cal.status = CalibrationStatus.PROVISIONAL
        per[category] = cal
    return Calibrator(version=version, per_category=per)
