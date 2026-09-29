"""Stage 5a — Semantic screen (embedding-based routing).

Embeds the item span and cosine-compares it to configured per-category example
phrases. Emits SIMILARITY findings (routing/prioritisation only — not a probability,
per response §3.3) and returns the set of categories that clear `route_threshold`, so
only those reach the LLM. This minimises what is sent to the model (data minimisation)
and its cost.

`TextEmbedder` is the swappable port; `SbertEmbedder` lazy-imports
`sentence_transformers`. Tests inject a fake embedder, so no model download is needed.
"""

from __future__ import annotations

import math
import threading
from typing import Any, Protocol, runtime_checkable

from libs.schemas import (
    CalibrationStatus,
    EvidenceLocation,
    Finding,
    ScoreType,
)

_DETECTOR_VERSION = "semantic-0.1"

# Process-level model cache: the SBERT model is expensive to load, so load each model
# name once per process and share it across jobs/threads (build_context runs per job).
_MODEL_CACHE: dict[str, Any] = {}
_MODEL_LOCK = threading.Lock()


@runtime_checkable
class TextEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...


class SbertEmbedder(TextEmbedder):
    """Sentence-Transformers embedder (lazy import)."""

    def __init__(self, model_name: str) -> None:
        # Load once per (process, model_name); reuse the cached instance thereafter.
        with _MODEL_LOCK:
            model = _MODEL_CACHE.get(model_name)
            if model is None:
                from sentence_transformers import (  # lazy: heavy dependency
                    SentenceTransformer,
                )

                model = SentenceTransformer(model_name)
                _MODEL_CACHE[model_name] = model
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticScreen:
    def __init__(
        self,
        embedder: TextEmbedder,
        examples: dict[str, list[str]],
        route_threshold: float,
        threshold_version: str,
    ) -> None:
        self._embedder = embedder
        self._route_threshold = route_threshold
        self._threshold_version = threshold_version
        # Precompute example embeddings once per category.
        self._category_examples: dict[str, list[list[float]]] = {}
        for category, phrases in examples.items():
            if phrases:
                self._category_examples[category] = embedder.embed(phrases)

    def screen(
        self, source_id: str, text: str
    ) -> tuple[list[Finding], set[str], dict[str, float]]:
        """Return (SIMILARITY findings, categories to route, best cosine per category).

        The per-category scores cover EVERY configured category (routed or not) so the
        UI can show why each did or did not clear the route threshold — a content-free
        reasoning trace.
        """
        if not text.strip() or not self._category_examples:
            return [], set(), {}
        item_vector = self._embedder.embed([text])[0]
        findings: list[Finding] = []
        routed: set[str] = set()
        scores: dict[str, float] = {}
        for category in sorted(self._category_examples):
            best = max(
                cosine(item_vector, example)
                for example in self._category_examples[category]
            )
            scores[category] = best
            if best >= self._route_threshold:
                routed.add(category)
                findings.append(
                    Finding(
                        source_id=source_id,
                        finding_id=f"semantic-{category}",
                        category=category,
                        reason_code="semantic_route",
                        reason_text=f"cosine {best:.2f} >= route threshold",
                        score_type=ScoreType.SIMILARITY,
                        band=None,  # routing signal, not a flag band
                        calibration_status=CalibrationStatus.NOT_APPLICABLE,
                        evidence_location=EvidenceLocation(
                            char_start=0, char_end=len(text)
                        ),
                        detector_version=_DETECTOR_VERSION,
                        threshold_version=self._threshold_version,
                        score=best,  # cosine 0-1 (not a probability)
                    )
                )
        return findings, routed, scores
