"""Semantic screen routing (fake embedder — no SBERT install needed)."""

from __future__ import annotations

import sys
import types

import pytest

from libs.schemas import ScoreType
from pipelines.workstream1_sensitive import semantic
from pipelines.workstream1_sensitive.semantic import SbertEmbedder, SemanticScreen, cosine


def test_sbert_model_loaded_once_per_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SBERT model is cached per (process, model_name) — loaded once, then reused."""
    calls = {"n": 0}

    class _FakeST:
        def __init__(self, name: str) -> None:
            calls["n"] += 1

        def encode(self, texts: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
            return [[0.0] for _ in texts]

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = _FakeST  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    semantic._MODEL_CACHE.clear()

    SbertEmbedder("model-x")
    SbertEmbedder("model-x")  # second construction must reuse the cached model
    assert calls["n"] == 1
    SbertEmbedder("model-y")  # a different model name loads once more
    assert calls["n"] == 2
    semantic._MODEL_CACHE.clear()


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
    findings, routed, scores = screen.screen("x", "the item text")
    assert routed == {"financial"}
    assert len(findings) == 1
    assert findings[0].score_type is ScoreType.SIMILARITY
    assert findings[0].band is None
    assert 0.0 <= (findings[0].score or 0.0) <= 1.0
    # scores cover EVERY category (routed or not) for the reasoning trace.
    assert set(scores) == {"financial", "health"}
    assert scores["health"] < 0.8  # below threshold -> not routed


def test_screen_empty_text_routes_nothing() -> None:
    screen = SemanticScreen(_FakeEmbedder({}), {}, 0.5, "sem-0")
    findings, routed, scores = screen.screen("x", "   ")
    assert findings == []
    assert routed == set()
    assert scores == {}
