"""AnthropicProvider — inference against Anthropic's Messages API.

A selectable alternative to the OpenAI-compatible `OpenWeightProvider` (Anthropic's API
is NOT OpenAI-compatible: `/v1/messages`, `x-api-key`, `anthropic-version`, and a
`content: [{type, text}]` reply). One category is scored per request via a constrained
JSON reply {"score": 0-100}; greedy (temperature 0) for reproducibility. Only the minimal
span is sent (data minimisation).

Egress: a managed endpoint (`is_local=False`) requires `approval_written` (Contract 2) —
the same gate as every other provider. The HTTP client is injectable so unit tests run
with no network; the real client lazy-imports `httpx`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from libs.inference.base import (
    SCORE_SYSTEM_PROMPT,
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    ensure_egress_allowed,
    parse_assessment,
    score_user_content,
)
from libs.schemas import CalibrationStatus

_ANTHROPIC_VERSION = "2023-06-01"  # stable Messages API version header


@runtime_checkable
class MessagesClient(Protocol):
    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a Messages payload and return the parsed JSON response."""
        ...


class HttpAnthropicClient(MessagesClient):
    """Real Anthropic Messages client (lazy-imports httpx)."""

    def __init__(
        self,
        base_url: str = "https://api.anthropic.com",
        api_key: str | None = None,
        timeout: float = 30.0,
        api_version: str = _ANTHROPIC_VERSION,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._api_version = api_version

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx  # lazy: only needed for a real endpoint

        headers = {
            "content-type": "application/json",
            "anthropic-version": self._api_version,
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
        response = httpx.post(
            f"{self._base_url}/v1/messages",
            json=payload,
            headers=headers,
            timeout=self._timeout,  # timeout on every external call (performance rule)
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


class AnthropicProvider(InferenceProvider):
    """Scores one category per request via a constrained JSON reply {"score": 0-100}."""

    def __init__(
        self,
        client: MessagesClient,
        model_version: str,
        is_local: bool,
        approval_written: bool,
        max_tokens: int = 64,
    ) -> None:
        self._client = client
        self._model_version = model_version
        self._is_local = is_local
        self._approval_written = approval_written
        self._max_tokens = max_tokens

    @property
    def is_local(self) -> bool:
        return self._is_local

    def _build_payload(self, request: InferenceRequest) -> dict[str, Any]:
        # Greedy, minimal span only. Anthropic has no response_format; constrain via prompt.
        return {
            "model": self._model_version,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "system": SCORE_SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": score_user_content(request.category, request.text)}
            ],
        }

    @staticmethod
    def _parse(response: dict[str, Any]) -> tuple[float, str | None]:
        blocks = response.get("content") or []
        text = next((b.get("text", "") for b in blocks if b.get("type") == "text"), "")
        return parse_assessment(text)  # tolerates markdown fences / trailing prose

    def assess(self, request: InferenceRequest) -> InferenceResult:
        ensure_egress_allowed(request, self._approval_written)
        response = self._client.create(self._build_payload(request))
        score, evidence = self._parse(response)
        return InferenceResult(
            score=score,
            evidence=evidence,
            model_version=self._model_version,
            calibration_status=CalibrationStatus.NOT_CALIBRATED,
        )
