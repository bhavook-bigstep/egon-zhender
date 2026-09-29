"""MockProvider — a deterministic, local inference stub for the skeleton.

It simulates a semantic model: it scores a category high when that category's
configured hint token appears in the span, and low otherwise. This keeps the
walking-skeleton end-to-end run deterministic and its truth set clean, with no real
model and no data egress. The real open-weight provider replaces it behind the same
port in Phase 2.
"""

from __future__ import annotations

from libs.inference.base import (
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    ensure_egress_allowed,
)
from libs.schemas import CalibrationStatus

_HIT_SCORE = 90.0
_MISS_SCORE = 5.0


class MockProvider(InferenceProvider):
    def __init__(
        self,
        model_version: str,
        approval_written: bool,
        hints: dict[str, str],
    ) -> None:
        self._model_version = model_version
        self._approval_written = approval_written
        self._hints = hints

    @property
    def is_local(self) -> bool:
        return True  # the mock runs in-process; nothing leaves the boundary

    def assess(self, request: InferenceRequest) -> InferenceResult:
        ensure_egress_allowed(request, self._approval_written)
        hint = self._hints.get(request.category)
        matched = hint is not None and hint.lower() in request.text.lower()
        score = _HIT_SCORE if matched else _MISS_SCORE
        return InferenceResult(
            score=score,
            model_version=self._model_version,
            calibration_status=CalibrationStatus.NOT_CALIBRATED,
        )
