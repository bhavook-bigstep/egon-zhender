"""Semantic screen routing (fake embedder — no SBERT install needed)."""

from __future__ import annotations

from libs.schemas import ScoreType
from pipelines.workstream1_sensitive.semantic import SemanticScreen, cosine


class _FakeEmbedder:
    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._mapping[text] for text in texts]


def test_cosine_basic() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_screen_routes_only_above_threshold() -> None:
    mapping = {
        "fin example": [1.0, 0.0],
        "health example": [0.0, 1.0],
        "the item text": [0.9, 0.1],
    }
    screen = SemanticScreen(
        embedder=_FakeEmbedder(mapping),
        examples={"financial": ["fin example"], "health": ["health example"]},
        route_threshold=0.8,
        threshold_version="sem-0",
    )
    findings, routed = screen.screen("x", "the item text")
    assert routed == {"financial"}
    assert len(findings) == 1
    assert findings[0].score_type is ScoreType.SIMILARITY
    assert findings[0].band is None
    assert 0.0 <= (findings[0].score or 0.0) <= 1.0


def test_screen_empty_text_routes_nothing() -> None:
    screen = SemanticScreen(_FakeEmbedder({}), {}, 0.5, "sem-0")
    findings, routed = screen.screen("x", "   ")
    assert findings == []
    assert routed == set()
