"""Stage 5b — Assess (LLM classification over routed categories).

For each category routed in by the semantic screen (or all categories when the screen
is disabled), send the minimal span to the `InferenceProvider` and emit a MODEL_SCORE
finding when the raw score clears the flag threshold. Band and calibration status are
assigned centrally after calibration (`score.finalize_scored`). Only the minimal span
is sent — never the whole document (data minimisation). `crosses_boundary` is derived
from the provider (`is_local`), so the egress gate is fail-safe by default (Contract 2).
"""

from __future__ import annotations

from collections.abc import Iterable

from libs.inference.base import InferenceProvider, InferenceRequest
from libs.minimisation import load_key, mask_identifiers
from libs.schemas import (
    EvidenceLocation,
    Finding,
    ScoreType,
    ScoringConfig,
)
from pipelines.workstream1_sensitive.extract import ExtractedText

# Minimal span sent to the model, in characters (data minimisation).
_MAX_SPAN_CHARS = 512


def assess(
    extracted: ExtractedText,
    categories: Iterable[str],
    scoring: ScoringConfig,
    provider: InferenceProvider,
    hash_key_env: str | None = None,
    max_span_chars: int = _MAX_SPAN_CHARS,
) -> list[Finding]:
    """Return raw MODEL_SCORE findings for categories that clear the flag threshold.

    On a boundary-crossing provider the span is identifier-masked with the EZ-held key
    before it leaves the boundary (Contract 2); missing key → fail closed.
    """
    if not extracted.text.strip():
        return []
    head = extracted.text[:max_span_chars]  # unmasked head — used to LOCATE the evidence
    crosses_boundary = not provider.is_local
    sent = mask_identifiers(head, load_key(hash_key_env)) if crosses_boundary else head
    whole_span = EvidenceLocation(char_start=0, char_end=len(head))
    findings: list[Finding] = []
    for category in categories:
        request = InferenceRequest(
            source_id=extracted.source_id,
            category=category,
            span_location=whole_span,
            text=sent,
            crosses_boundary=crosses_boundary,
        )
        result = provider.assess(request)
        if result.score < scoring.flag_threshold:
            continue
        # Pin the finding to the SPECIFIC substring the model flagged, when we can locate it
        # (the quote is used only to find offsets — never stored). Falls back to the whole
        # head span when the model gives no quote or it was masked out of the unmasked text.
        location, reason = _locate(result.evidence, head, category, result.score, whole_span)
        findings.append(
            Finding(
                source_id=extracted.source_id,
                finding_id=f"model-{category}",
                category=category,
                reason_code="model_flag",
                reason_text=reason,
                score_type=ScoreType.MODEL_SCORE,
                band=None,  # assigned after calibration
                calibration_status=result.calibration_status,
                evidence_location=location,
                detector_version=result.model_version,
                score=result.score,
            )
        )
    return findings


def _locate(
    evidence: str | None,
    head: str,
    category: str,
    score: float,
    whole_span: EvidenceLocation,
) -> tuple[EvidenceLocation, str]:
    """Resolve the model's evidence quote to a precise location + a specific reason.

    Returns the whole-span location + a generic reason when the quote is absent or cannot
    be found in the unmasked head (e.g. it referenced a masked identifier)."""
    if evidence:
        index = head.find(evidence)
        if index >= 0:
            return (
                EvidenceLocation(char_start=index, char_end=index + len(evidence)),
                f"model flagged a specific {category} instance (score {score:.0f})",
            )
    return whole_span, f"model score {score:.0f} >= flag threshold"
