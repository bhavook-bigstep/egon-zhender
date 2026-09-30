"""AnthropicProvider (fake Messages client — no network)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.inference.anthropic import AnthropicProvider
from libs.inference.base import InferenceEgressError, InferenceRequest
from libs.schemas import CalibrationStatus, EvidenceLocation


class _FakeClient:
    def __init__(self, text: str) -> None:
        self._text = text
        self.last_payload: dict[str, Any] | None = None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_payload = payload
        return {"content": [{"type": "text", "text": self._text}]}


def _request(crosses_boundary: bool) -> InferenceRequest:
    return InferenceRequest(
        source_id="x",
        category="financial",
        span_location=EvidenceLocation(),
        text="the minimal span",
        crosses_boundary=crosses_boundary,
    )


def test_parses_json_score_and_builds_minimal_payload() -> None:
    client = _FakeClient('{"score": 88}')
    provider = AnthropicProvider(client, "claude-x", is_local=False, approval_written=True)
    result = provider.assess(_request(True))
    assert result.score == 88.0
    assert result.calibration_status is CalibrationStatus.NOT_CALIBRATED
    assert client.last_payload is not None
    assert client.last_payload["temperature"] == 0  # greedy → reproducible
    assert client.last_payload["model"] == "claude-x"
    assert "max_tokens" in client.last_payload
    assert any("the minimal span" in m["content"] for m in client.last_payload["messages"])


def test_parses_score_from_prose_fallback() -> None:
    """If the model adds prose despite instructions, the first integer is recovered."""
    provider = AnthropicProvider(
        _FakeClient("The score is 42 out of 100."), "m", is_local=False, approval_written=True
    )
    assert provider.assess(_request(True)).score == 42.0


def test_score_is_clamped() -> None:
    provider = AnthropicProvider(
        _FakeClient('{"score": 250}'), "m", is_local=False, approval_written=True
    )
    assert provider.assess(_request(True)).score == 100.0


def test_egress_blocked_without_approval() -> None:
    provider = AnthropicProvider(
        _FakeClient('{"score": 5}'), "m", is_local=False, approval_written=False
    )
    with pytest.raises(InferenceEgressError):
        provider.assess(_request(True))


def test_is_local_property() -> None:
    provider = AnthropicProvider(
        _FakeClient('{"score": 5}'), "m", is_local=False, approval_written=False
    )
    assert provider.is_local is False
