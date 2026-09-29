"""OpenWeightProvider (fake OpenAI-compatible client — no network)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.inference.base import InferenceEgressError, InferenceRequest
from libs.inference.openweight import OpenWeightProvider
from libs.schemas import CalibrationStatus, EvidenceLocation


class _FakeClient:
    def __init__(self, score: float) -> None:
        self._score = score
        self.last_payload: dict[str, Any] | None = None

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_payload = payload
        return {"choices": [{"message": {"content": f'{{"score": {self._score}}}'}}]}


def _request(crosses_boundary: bool) -> InferenceRequest:
    return InferenceRequest(
        source_id="x",
        category="financial",
        span_location=EvidenceLocation(),
        text="the minimal span",
        crosses_boundary=crosses_boundary,
    )


def test_parses_score_and_builds_minimal_structured_payload() -> None:
    client = _FakeClient(90)
    provider = OpenWeightProvider(client, "qwen", is_local=True, approval_written=False)
    result = provider.assess(_request(False))
    assert result.score == 90.0
    assert result.calibration_status is CalibrationStatus.NOT_CALIBRATED
    assert client.last_payload is not None
    assert client.last_payload["temperature"] == 0  # greedy → reproducible
    assert "response_format" in client.last_payload  # structured output
    assert any("the minimal span" in m["content"] for m in client.last_payload["messages"])


def test_is_local_property() -> None:
    provider = OpenWeightProvider(_FakeClient(50), "m", is_local=False, approval_written=False)
    assert provider.is_local is False


def test_egress_blocked_without_approval() -> None:
    provider = OpenWeightProvider(_FakeClient(50), "m", is_local=False, approval_written=False)
    with pytest.raises(InferenceEgressError):
        provider.assess(_request(True))


def test_egress_allowed_with_written_approval() -> None:
    provider = OpenWeightProvider(_FakeClient(70), "m", is_local=False, approval_written=True)
    assert provider.assess(_request(True)).score == 70.0
