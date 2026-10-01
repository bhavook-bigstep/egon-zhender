"""Inference boundary: egress is blocked without written approval (Contract 2)."""

from __future__ import annotations

import pytest

from libs.inference.base import (
    InferenceEgressError,
    InferenceRequest,
    parse_assessment,
)
from libs.inference.mock import MockProvider
from libs.schemas import EvidenceLocation


def test_parse_assessment_score_and_evidence() -> None:
    score, evidence = parse_assessment('{"score": 90, "evidence": "swift bic MNBUS47KZX"}')
    assert score == 90.0
    assert evidence == "swift bic MNBUS47KZX"


def test_parse_assessment_tolerates_fences_and_missing_evidence() -> None:
    score, evidence = parse_assessment('```json\n{"score": 82}\n```')
    assert score == 82.0
    assert evidence is None
    # empty evidence string → None (nothing to locate)
    assert parse_assessment('{"score": 70, "evidence": ""}') == (70.0, None)


def _request(crosses_boundary: bool) -> InferenceRequest:
    return InferenceRequest(
        source_id="x",
        category="financial",
        span_location=EvidenceLocation(),
        text="span",
        crosses_boundary=crosses_boundary,
    )


def test_gate_blocks_boundary_crossing_without_approval() -> None:
    provider = MockProvider("m", approval_written=False, hints={})
    with pytest.raises(InferenceEgressError):
        provider.assess(_request(crosses_boundary=True))


def test_gate_allows_with_written_approval() -> None:
    provider = MockProvider("m", approval_written=True, hints={})
    result = provider.assess(_request(crosses_boundary=True))
    assert result.model_version == "m"


def test_local_inference_never_blocked() -> None:
    provider = MockProvider("m", approval_written=False, hints={})
    result = provider.assess(_request(crosses_boundary=False))
    assert result.model_version == "m"
