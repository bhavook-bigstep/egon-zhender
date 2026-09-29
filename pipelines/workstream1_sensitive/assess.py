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
) -> list[Finding]:
    """Return raw MODEL_SCORE findings for categories that clear the flag threshold.

    On a boundary-crossing provider the span is identifier-masked with the EZ-held key
    before it leaves the boundary (Contract 2); missing key → fail closed.
    """
    if not extracted.text.strip():
        return []
    span = extracted.text[:_MAX_SPAN_CHARS]
    crosses_boundary = not provider.is_local
    if crosses_boundary:
        span = mask_identifiers(span, load_key(hash_key_env))
    location = EvidenceLocation(char_start=0, char_end=len(span))
    findings: list[Finding] = []
    for category in categories:
        request = InferenceRequest(
            source_id=extracted.source_id,
            category=category,
            span_location=location,
            text=span,
            crosses_boundary=crosses_boundary,
        )
        result = provider.assess(request)
        if result.score < scoring.flag_threshold:
            continue
        findings.append(
            Finding(
                source_id=extracted.source_id,
                finding_id=f"model-{category}",
                category=category,
                reason_code="model_flag",
                reason_text=f"model score {result.score:.0f} >= flag threshold",
                score_type=ScoreType.MODEL_SCORE,
                band=None,  # assigned after calibration
                calibration_status=result.calibration_status,
                evidence_location=location,
                detector_version=result.model_version,
                score=result.score,
            )
        )
    return findings
