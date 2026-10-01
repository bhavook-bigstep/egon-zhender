"""InferenceProvider port (Part 4).

The single egress point for model inference. Any request that would cross the
approved boundary must be refused unless written approval is configured
(Contract 2 / `.claude/rules/privacy-sensitive-data.md`). The baseline provider is
open-weight on controlled infra; a managed endpoint drops in behind the same port,
approval-gated.
"""

from __future__ import annotations

import json
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
    "`evidence` is the SHORTEST exact substring from the span that shows it (verbatim, "
    "copied character-for-character), or an empty string if none. "
    'Reply ONLY as compact JSON {"score": <integer 0-100>, "evidence": "<substring>"}.'
)

_SCORE_JSON_RE = re.compile(r'"score"\s*:\s*(-?\d+)')
_INT_RE = re.compile(r"-?\d+")
_EVIDENCE_RE = re.compile(r'"evidence"\s*:\s*"((?:[^"\\]|\\.)*)"')


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


def parse_assessment(text: str) -> tuple[float, str | None]:
    """Extract (score, evidence substring) from a model reply. Tolerant of fences/prose.

    The evidence quote lets the assess stage point the finding at the SPECIFIC span the
    model keyed on, instead of the whole document. It is used ONLY to locate offsets and
    is never stored (Contract 2/3). Returns None evidence when absent or empty.
    """
    score = parse_score_text(text)
    evidence: str | None = None
    match = _EVIDENCE_RE.search(text)
    if match:
        raw = match.group(1)
        try:  # un-escape JSON string escapes (\", \\, \n, …)
            evidence = json.loads(f'"{raw}"')
        except ValueError:
            evidence = raw
        evidence = (evidence or "").strip() or None
    return score, evidence


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
    # The exact substring the model flagged (to locate a precise evidence span; never stored).
    evidence: str | None = Field(default=None, repr=False)


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
