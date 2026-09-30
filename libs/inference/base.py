"""InferenceProvider port (Part 4).

The single egress point for model inference. Any request that would cross the
approved boundary must be refused unless written approval is configured
(Contract 2 / `.claude/rules/privacy-sensitive-data.md`). The baseline provider is
open-weight on controlled infra; a managed endpoint drops in behind the same port,
approval-gated.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from libs.schemas import CalibrationStatus, EvidenceLocation

# Shared scoring prompt so every provider asks the SAME question (no per-provider drift).
# Presence-oriented: the golden truth flags a category when a concrete identifier/datum of
# that category is present, so the model scores PRESENCE, not topical relevance.
SCORE_SYSTEM_PROMPT = (
    "You are a data-privacy classifier. Score 0-100 how likely the text contains any "
    "personal or sensitive data of the given category — including specific identifiers or "
    "numbers (financial: account/card/IBAN/SWIFT/BIC/routing/PIN; government_id: SSN/"
    "passport/licence/tax-id/plate/VIN; health: medical-record/insurance/diagnosis/blood "
    "type). Output ~100 if at least one clear instance is present, near 0 if none. "
    'Reply ONLY as compact JSON {"score": <integer 0-100>}.'
)

_SCORE_JSON_RE = re.compile(r'"score"\s*:\s*(-?\d+)')
_INT_RE = re.compile(r"-?\d+")


def score_user_content(category: str, text: str) -> str:
    """The user turn sent to any scoring provider (minimal span only)."""
    return f"category: {category}\nspan: {text}"


def parse_score_text(text: str) -> float:
    """Extract a 0-100 score from a model reply, tolerating markdown fences / prose.

    Prefers the `"score": N` field; falls back to the first integer. Clamped to [0, 100].
    """
    match = _SCORE_JSON_RE.search(text) or _INT_RE.search(text)
    if match is None:
        raise ValueError("no score in model reply")
    value = float(match.group(1) if match.re is _SCORE_JSON_RE else match.group())
    return max(0.0, min(100.0, value))


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
