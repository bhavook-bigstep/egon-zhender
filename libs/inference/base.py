"""InferenceProvider port (Part 4).

The single egress point for model inference. Any request that would cross the
approved boundary must be refused unless written approval is configured
(Contract 2 / `.claude/rules/privacy-sensitive-data.md`). The baseline provider is
open-weight on controlled infra; a managed endpoint drops in behind the same port,
approval-gated.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from libs.schemas import CalibrationStatus, EvidenceLocation


class InferenceEgressError(RuntimeError):
    """Raised when a request would cross the boundary without written approval."""


class InferenceRequest(BaseModel):
    """A single assessment request. `text` is the minimal span, in-memory only."""

    source_id: str
    category: str
    span_location: EvidenceLocation
    text: str = Field(repr=False)  # never logged; excluded from repr
    crosses_boundary: bool = False


class InferenceResult(BaseModel):
    score: float  # 0-100
    model_version: str
    calibration_status: CalibrationStatus = CalibrationStatus.NOT_CALIBRATED


@runtime_checkable
class InferenceProvider(Protocol):
    @property
    def is_local(self) -> bool:
        """True when inference runs on controlled/dedicated infra (no egress)."""
        ...

    def assess(self, request: InferenceRequest) -> InferenceResult:
        """Return a score for the request, or raise InferenceEgressError."""
        ...


def ensure_egress_allowed(request: InferenceRequest, approval_written: bool) -> None:
    """Guard: block boundary-crossing inference without written approval."""
    if request.crosses_boundary and not approval_written:
        raise InferenceEgressError(
            f"inference for {request.source_id} would cross the boundary without "
            "written approval (Contract 2)"
        )
