"""PresidioHttpEngine (fake analyze client — no container needed)."""

from __future__ import annotations

from typing import Any

import pytest

from libs.schemas import (
    CustomRecogniserConfig,
    DetectConfig,
    ExceptionCode,
    PatternSpec,
    ScoreType,
)
from pipelines.workstream1_sensitive.detect import build_detection_engine
from pipelines.workstream1_sensitive.detect_presidio_http import PresidioHttpEngine
from pipelines.workstream1_sensitive.errors import PipelineItemError
from pipelines.workstream1_sensitive.extract import ExtractedText

CFG = DetectConfig(
    engine="presidio_http",
    presidio_url="http://presidio",
    category_map={"CREDIT_CARD": "financial", "PERSON": "health"},
    deterministic_entities=["CREDIT_CARD"],
)


class _FakeClient:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results
        self.last_payload: dict[str, Any] | None = None

    def analyze(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.last_payload = payload
        return self._results


def test_maps_deterministic_and_classifier_and_skips_unmapped() -> None:
    client = _FakeClient(
        [
            {"entity_type": "CREDIT_CARD", "start": 5, "end": 21, "score": 1.0},
            {"entity_type": "PERSON", "start": 0, "end": 4, "score": 0.85},
            {"entity_type": "URL", "start": 30, "end": 40, "score": 0.9},
        ]
    )
    engine = PresidioHttpEngine(CFG, client=client)
    findings = engine.analyze(ExtractedText(source_id="x", text="Jane card 4111111111111111"))
    by_cat = {f.category: f for f in findings}
    assert set(by_cat) == {"financial", "health"}  # URL skipped
    assert by_cat["financial"].score_type is ScoreType.DETERMINISTIC_MATCH
    assert by_cat["financial"].score is None
    assert by_cat["health"].score_type is ScoreType.CLASSIFIER_SCORE
    assert by_cat["health"].score == 85.0
    assert client.last_payload is not None
    assert client.last_payload["text"] == "Jane card 4111111111111111"


def test_transport_error_becomes_typed_exception() -> None:
    class _Boom:
        def analyze(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
            raise ConnectionError("presidio down")

    engine = PresidioHttpEngine(CFG, client=_Boom())
    with pytest.raises(PipelineItemError) as exc:
        engine.analyze(ExtractedText(source_id="x", text="anything"))
    assert exc.value.code is ExceptionCode.DETECTION_ERROR


def test_factory_builds_presidio_http() -> None:
    engine = build_detection_engine(CFG)
    assert isinstance(engine, PresidioHttpEngine)


def test_engine_without_url_or_client_raises() -> None:
    with pytest.raises(ValueError):
        PresidioHttpEngine(DetectConfig(engine="presidio_http"))


def test_custom_recognizers_sent_as_ad_hoc_and_mapped() -> None:
    """Config custom_recognizers are added to the /analyze request (ad-hoc) in Presidio's
    from_dict shape, and their entity maps to a category via category_map."""
    cfg = DetectConfig(
        engine="presidio_http",
        presidio_url="http://presidio",
        custom_recognizers=[
            CustomRecogniserConfig(
                name="swift_bic_recognizer",
                supported_entity="SWIFT_BIC",
                patterns=[PatternSpec(name="swift", regex=r"\b[A-Z]{4}[A-Z0-9]{4,7}\b", score=0.5)],
                context=["swift", "transfer"],
            )
        ],
        category_map={"SWIFT_BIC": "financial"},
    )
    client = _FakeClient([{"entity_type": "SWIFT_BIC", "start": 0, "end": 10, "score": 0.85}])
    findings = PresidioHttpEngine(cfg, client=client).analyze(
        ExtractedText(source_id="x", text="MNBUS47KZX transfer")
    )
    assert client.last_payload is not None
    ad_hoc = client.last_payload["ad_hoc_recognizers"]
    assert ad_hoc[0]["supported_entity"] == "SWIFT_BIC"
    assert ad_hoc[0]["patterns"][0]["regex"] == r"\b[A-Z]{4}[A-Z0-9]{4,7}\b"
    assert ad_hoc[0]["context"] == ["swift", "transfer"]
    assert findings and findings[0].category == "financial"  # custom entity → category


def test_no_ad_hoc_key_when_no_custom_recognizers() -> None:
    """Default: the payload carries no ad_hoc_recognizers (Presidio uses its built-ins only)."""
    client = _FakeClient([])
    PresidioHttpEngine(CFG, client=client).analyze(ExtractedText(source_id="x", text="hi"))
    assert client.last_payload is not None
    assert "ad_hoc_recognizers" not in client.last_payload
