"""PresidioHttpEngine — detection via a presidio-analyzer container.

POSTs `{text, language, score_threshold}` to `{base_url}/analyze` and maps the returned
recogniser results to findings (reusing `map_presidio_results`). The HTTP client is
injectable so unit tests run against a fake with no container. Only the item text (a copy)
is sent to the local service; responses are not logged verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from libs.schemas import DetectConfig, ExceptionCode, Finding
from pipelines.workstream1_sensitive.detect_presidio import map_presidio_results
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract import ExtractedText


@dataclass
class _Result:
    entity_type: str
    start: int
    end: int
    score: float


@runtime_checkable
class AnalyzeClient(Protocol):
    def analyze(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """POST an analyze request and return the list of recogniser results."""
        ...


class HttpAnalyzeClient(AnalyzeClient):
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._url = base_url.rstrip("/") + "/analyze"
        self._timeout = timeout

    def analyze(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        import httpx  # lazy

        response = httpx.post(self._url, json=payload, timeout=self._timeout)
        response.raise_for_status()
        result: list[dict[str, Any]] = response.json()
        return result


class PresidioHttpEngine:
    def __init__(self, cfg: DetectConfig, client: AnalyzeClient | None = None) -> None:
        self._cfg = cfg
        if client is not None:
            self._client: AnalyzeClient = client
        else:
            if not cfg.presidio_url:
                raise ValueError("presidio_http engine requires detect.presidio_url")
            self._client = HttpAnalyzeClient(cfg.presidio_url)

    def analyze(self, extracted: ExtractedText) -> list[Finding]:
        payload = {
            "text": extracted.text,
            "language": self._cfg.presidio_language,
            "score_threshold": self._cfg.presidio_score_threshold,
        }
        try:
            raw = self._client.analyze(payload)
        except PipelineItemError:
            raise
        except Exception as exc:  # transport/parse failure → typed, fail loud
            raise PipelineItemError(
                ExceptionCode.DETECTION_ERROR,
                f"presidio analyze failed for {extracted.source_id}",
            ) from exc
        results = [
            _Result(
                entity_type=item["entity_type"],
                start=int(item["start"]),
                end=int(item["end"]),
                score=float(item["score"]),
            )
            for item in raw
        ]
        return map_presidio_results(
            results, self._cfg, extracted.source_id, extracted.spans
        )
