"""User-managed custom recogniser store + config overlay (synthetic)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from libs.recognizers_store import (
    StoredRecognizer,
    apply_recognizer_overlay,
    load_recognizers,
    save_recognizers,
)
from libs.schemas import DetectConfig


def _rec(**kw: object) -> StoredRecognizer:
    base = dict(name="swift", supported_entity="SWIFT_BIC", category="financial", regex=r"\bX\b")
    base.update(kw)
    return StoredRecognizer(**base)  # type: ignore[arg-type]


def test_save_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "rec.json"
    save_recognizers([_rec(score=0.3, context=["swift", "transfer"])], p)
    got = load_recognizers(p)
    assert len(got) == 1
    assert got[0].supported_entity == "SWIFT_BIC" and got[0].context == ["swift", "transfer"]


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_recognizers(tmp_path / "nope.json") == []


def test_invalid_regex_rejected() -> None:
    with pytest.raises(ValidationError):
        _rec(regex="([")  # unbalanced


def test_score_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        _rec(score=1.5)


def test_apply_overlay_merges_into_detect(tmp_path: Path) -> None:
    p = tmp_path / "rec.json"
    save_recognizers([_rec(deterministic=True)], p)
    base = DetectConfig(engine="presidio_http", category_map={"US_SSN": "government_id"})
    merged = apply_recognizer_overlay(base, p)
    assert any(r.supported_entity == "SWIFT_BIC" for r in merged.custom_recognizers)
    assert merged.category_map["SWIFT_BIC"] == "financial"
    assert merged.category_map["US_SSN"] == "government_id"  # existing map preserved
    assert "SWIFT_BIC" in merged.deterministic_entities
    assert base.custom_recognizers == []  # original config untouched


def test_apply_overlay_noop_when_empty(tmp_path: Path) -> None:
    base = DetectConfig(engine="regex")
    assert apply_recognizer_overlay(base, tmp_path / "none.json") is base
