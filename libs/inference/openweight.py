"""OpenWeightProvider — inference against an OpenAI-compatible endpoint.

Targets a vLLM-style `/v1/chat/completions` server (open-weight model on
controlled/dedicated infra by default). Uses structured output (a JSON-schema /
`guided_choice` constraint) plus greedy decoding for reliable, reproducible
classification. The HTTP client is injectable so unit tests run against a fake with no
network; the real client lazy-imports `httpx`.

Egress: `crosses_boundary` is set by the caller from `is_local`; a managed endpoint
(`is_local=False`) additionally requires `approval_written` (Contract 2).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from libs.inference.base import (
    SCORE_SYSTEM_PROMPT,
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    ensure_egress_allowed,
    parse_score_text,
    score_user_content,
)
from libs.schemas import CalibrationStatus


@runtime_checkable
class ChatClient(Protocol):
    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a chat-completions payload and return the parsed JSON response."""
        ...


class HttpChatClient(ChatClient):
    """Real OpenAI-compatible client (lazy-imports httpx)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        chat_path: str = "/v1/chat/completions",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        # vLLM: /v1/chat/completions · Gemini shim: /chat/completions
        self._chat_path = "/" + chat_path.strip("/")

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx  # lazy: only needed for a real endpoint

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = httpx.post(
            f"{self._base_url}{self._chat_path}",
            json=payload,
            headers=headers,
            timeout=self._timeout,  # timeout on every external call (performance rule)
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


class OpenWeightProvider(InferenceProvider):
    """Scores one category per request via a constrained JSON response {"score": 0-100}."""

    def __init__(
        self,
        client: ChatClient,
        model_version: str,
        is_local: bool,
        approval_written: bool,
    ) -> None:
        self._client = client
        self._model_version = model_version
        self._is_local = is_local
        self._approval_written = approval_written

    @property
    def is_local(self) -> bool:
        return self._is_local

    def _build_payload(self, request: InferenceRequest) -> dict[str, Any]:
        # Structured output: constrain the reply to a single 0-100 integer score for the
        # requested category. Greedy (temperature 0) for reproducibility. Only the
        # minimal span is sent (data minimisation).
        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["score"],
        }
        return {
            "model": self._model_version,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SCORE_SYSTEM_PROMPT},
                {"role": "user", "content": score_user_content(request.category, request.text)},
            ],
            "response_format": {
                # `name` is required by the OpenAI json_schema spec and by Gemini's
                # OpenAI-compat shim; vLLM tolerates it. Keeps structured output portable.
                "type": "json_schema",
                "json_schema": {"name": "sensitivity_score", "schema": schema},
            },
        }

    @staticmethod
    def _parse_score(response: dict[str, Any]) -> float:
        content = response["choices"][0]["message"]["content"]
        return parse_score_text(content)

    def assess(self, request: InferenceRequest) -> InferenceResult:
        ensure_egress_allowed(request, self._approval_written)
        response = self._client.complete(self._build_payload(request))
        return InferenceResult(
            score=self._parse_score(response),
            model_version=self._model_version,
            calibration_status=CalibrationStatus.NOT_CALIBRATED,
        )
