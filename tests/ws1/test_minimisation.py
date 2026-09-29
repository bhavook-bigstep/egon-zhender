"""Identifier minimisation before hosted transfer + the egress boundary validator."""

from __future__ import annotations

import pytest

from libs.hashing import hash_identifier
from libs.inference.base import InferenceRequest, InferenceResult
from libs.minimisation import MinimisationKeyError, load_key, mask_identifiers
from libs.schemas import EvidenceLocation, InferenceConfig, ScoringConfig
from pipelines.workstream1_sensitive.assess import assess
from pipelines.workstream1_sensitive.extract import ExtractedText

KEY = b"unit-test-key"


def test_mask_identifiers_replaces_email_phone_linkedin() -> None:
    text = "reach jane.doe@example.com or +1 415 555 0199 or https://linkedin.com/in/jane"
    masked = mask_identifiers(text, KEY)
    assert "jane.doe@example.com" not in masked
    assert "linkedin.com/in/jane" not in masked
    assert "415 555 0199" not in masked
    assert "<email:" in masked and "<phone:" in masked and "<linkedin:" in masked


def test_hash_identifier_is_keyed_and_stable() -> None:
    assert hash_identifier("a@b.com", KEY) == hash_identifier("a@b.com", KEY)
    assert hash_identifier("a@b.com", KEY) != hash_identifier("a@b.com", b"other-key")


def test_load_key_missing_env_fails_closed() -> None:
    with pytest.raises(MinimisationKeyError):
        load_key(None)
    with pytest.raises(MinimisationKeyError):
        load_key("WS1_DEFINITELY_UNSET_KEY_ENV")


class _RemoteProvider:
    @property
    def is_local(self) -> bool:
        return False

    def __init__(self) -> None:
        self.seen_text: str | None = None

    def assess(self, request: InferenceRequest) -> InferenceResult:
        self.seen_text = request.text
        return InferenceResult(score=5.0, model_version="remote")


def test_assess_masks_identifiers_before_remote_call(monkeypatch) -> None:
    monkeypatch.setenv("WS1_TEST_HASH_KEY", "secret")
    provider = _RemoteProvider()
    extracted = ExtractedText(source_id="x", text="email jane.doe@example.com now")
    assess(extracted, ["financial"], ScoringConfig(), provider, "WS1_TEST_HASH_KEY")
    assert provider.seen_text is not None
    assert "jane.doe@example.com" not in provider.seen_text


def test_assess_remote_without_key_fails_closed() -> None:
    provider = _RemoteProvider()
    extracted = ExtractedText(source_id="x", text="email jane.doe@example.com")
    with pytest.raises(MinimisationKeyError):
        assess(extracted, ["financial"], ScoringConfig(), provider, None)


def test_inference_config_rejects_local_flag_with_remote_url() -> None:
    with pytest.raises(ValueError):
        InferenceConfig(
            provider="openweight",
            model_version="m",
            is_local=True,
            base_url="https://api.openai.com/v1",
        )


def test_inference_config_allows_local_url_with_local_flag() -> None:
    cfg = InferenceConfig(
        provider="openweight",
        model_version="m",
        is_local=True,
        base_url="http://localhost:8000/v1",
    )
    assert cfg.is_local is True


def test_evidence_location_default_is_empty() -> None:
    # sanity: EvidenceLocation is content-free by construction
    assert EvidenceLocation().model_dump() == {
        "page": None,
        "sheet": None,
        "cell": None,
        "char_start": None,
        "char_end": None,
    }
