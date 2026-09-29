"""Inference boundary: egress is blocked without written approval (Contract 2)."""

from __future__ import annotations

import pytest

from libs.inference.base import InferenceEgressError, InferenceRequest
from libs.inference.mock import MockProvider
from libs.schemas import EvidenceLocation


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
