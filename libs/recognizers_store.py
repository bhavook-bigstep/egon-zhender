"""User-managed custom Presidio recognisers (set via the admin UI).

Persists a small overlay of PatternRecognisers to a JSON file and merges it ON TOP OF the
config's `detect.custom_recognizers` (and `category_map`) at context-build time. This lets
an operator add entities/patterns without editing YAML.

Reproducibility note (Contract 4): the overlay is a mutable tuning layer — for a governed,
reproducible run the recognisers should be baked into the versioned config. The overlay
file lives under the git-ignored `poc/` and holds config-like data only (never PII).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from libs.checksums import SELECTABLE_VALIDATORS
from libs.schemas import ChecksumSpec, CustomRecogniserConfig, DetectConfig, PatternSpec

DEFAULT_STORE = Path("poc/custom_recognizers.json")


def store_path() -> Path:
    """Overlay file path (env-overridable)."""
    return Path(os.environ.get("WS1_RECOGNIZERS_FILE", str(DEFAULT_STORE)))


class StoredRecognizer(BaseModel):
    """One UI-defined recogniser (a single regex → one entity → one category)."""

    name: str
    supported_entity: str
    category: str
    regex: str
    score: float = Field(default=0.4, ge=0.0, le=1.0)
    context: list[str] = Field(default_factory=list)
    deterministic: bool = False  # regex is a validated/checksum format → DETERMINISTIC_MATCH
    # optional checksum: luhn | iban_mod97 | aba_routing | weighted_modulus (+ `checksum` params)
    validator: str | None = None
    checksum: ChecksumSpec | None = None

    @field_validator("regex")
    @classmethod
    def _valid_regex(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return value

    @field_validator("validator")
    @classmethod
    def _known_validator(cls, value: str | None) -> str | None:
        if value is not None and value not in SELECTABLE_VALIDATORS:
            raise ValueError(
                f"unknown validator: {value}; choose one of {SELECTABLE_VALIDATORS}"
            )
        return value

    @model_validator(mode="after")
    def _checksum_params_present(self) -> StoredRecognizer:
        # weighted_modulus is data-parameterised → it needs a `checksum` spec.
        if self.validator == "weighted_modulus" and self.checksum is None:
            raise ValueError("validator 'weighted_modulus' requires a 'checksum' spec")
        return self

    @field_validator("name", "supported_entity", "category")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


def load_recognizers(path: Path | None = None) -> list[StoredRecognizer]:
    target = path or store_path()
    if not target.exists():
        return []
    data = json.loads(target.read_text(encoding="utf-8"))
    return [StoredRecognizer.model_validate(item) for item in data]


def save_recognizers(items: list[StoredRecognizer], path: Path | None = None) -> None:
    target = path or store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump() for item in items]
    target.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def apply_recognizer_overlay(detect: DetectConfig, path: Path | None = None) -> DetectConfig:
    """Return a copy of `detect` with the UI overlay merged into custom_recognizers,
    category_map, and deterministic_entities. No overlay → the config is returned unchanged."""
    overlay = load_recognizers(path)
    if not overlay:
        return detect
    extra = [
        CustomRecogniserConfig(
            name=rec.name,
            supported_entity=rec.supported_entity,
            patterns=[PatternSpec(name=rec.name, regex=rec.regex, score=rec.score)],
            context=rec.context,
            validator=rec.validator,
            checksum=rec.checksum,
        )
        for rec in overlay
    ]
    category_map = dict(detect.category_map)
    deterministic = list(detect.deterministic_entities)
    for rec in overlay:
        category_map[rec.supported_entity] = rec.category
        if rec.deterministic and rec.supported_entity not in deterministic:
            deterministic.append(rec.supported_entity)
    return detect.model_copy(
        update={
            "custom_recognizers": list(detect.custom_recognizers) + extra,
            "category_map": category_map,
            "deterministic_entities": deterministic,
        }
    )
