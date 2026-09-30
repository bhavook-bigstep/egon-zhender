"""Tests for the pure checksum validators in ``libs.checksums``.

Synthetic values only; no real PII. The IBAN ``GB82WEST12345698765432`` is the
canonical ISO 13616 mod-97 example value.
"""

from __future__ import annotations

from libs.checksums import VALIDATORS, aba_routing, iban_mod97, luhn


def test_luhn_valid() -> None:
    assert luhn("4111111111111111") is True


def test_luhn_invalid() -> None:
    assert luhn("4111111111111112") is False


def test_luhn_empty() -> None:
    assert luhn("") is False


def test_aba_routing_valid() -> None:
    assert aba_routing("021000021") is True


def test_aba_routing_invalid() -> None:
    assert aba_routing("021000020") is False


def test_aba_routing_wrong_length() -> None:
    assert aba_routing("12345") is False


def test_iban_mod97_valid() -> None:
    assert iban_mod97("GB82WEST12345698765432") is True


def test_iban_mod97_invalid_one_char_changed() -> None:
    assert iban_mod97("GB82WEST12345698765433") is False


def test_iban_mod97_empty() -> None:
    assert iban_mod97("") is False


def test_validators_map() -> None:
    assert VALIDATORS == {
        "luhn": luhn,
        "iban_mod97": iban_mod97,
        "aba_routing": aba_routing,
    }


# ---- weighted_modulus (declarative, no user code) ----------------------------
from libs.checksums import SELECTABLE_VALIDATORS, resolve_validator, weighted_modulus  # noqa: E402
from libs.schemas import ChecksumSpec  # noqa: E402


def test_weighted_sum_reproduces_aba() -> None:
    # ABA: weighted sum, mod 10, weights 3,7,1 from the left.
    spec = ChecksumSpec(mode="weighted_sum", modulus=10, weights=[3, 7, 1], align="left")
    assert weighted_modulus("011000015", spec) is True   # Federal Reserve Boston
    assert weighted_modulus("011000016", spec) is False  # one digit off → fails
    assert aba_routing("011000015") == weighted_modulus("011000015", spec)


def test_integer_mode_reproduces_iban() -> None:
    # IBAN: integer, mod 97, remainder 1, alphanumeric, rotate 4.
    spec = ChecksumSpec(mode="integer", modulus=97, expect=1, alphabet="alnum", rotate=4)
    assert weighted_modulus("GB82WEST12345698765432", spec) is True
    assert weighted_modulus("GB82WEST12345698765433", spec) is False


def test_weighted_modulus_malformed_returns_false() -> None:
    spec = ChecksumSpec(mode="weighted_sum", modulus=10, weights=[1])
    assert weighted_modulus("", spec) is False          # empty
    assert weighted_modulus("12A4", spec) is False       # letter under digits-only alphabet


def test_spec_rejects_incoherent_params() -> None:
    import pytest

    with pytest.raises(ValueError):
        ChecksumSpec(modulus=10, expect=10, weights=[1])  # expect must be < modulus
    with pytest.raises(ValueError):
        ChecksumSpec(mode="weighted_sum", modulus=11, weights=[])  # needs weights


def test_resolve_validator() -> None:
    assert "weighted_modulus" in SELECTABLE_VALIDATORS
    named = resolve_validator("luhn", None)
    assert named is not None and named.name == "luhn"
    spec = ChecksumSpec(mode="weighted_sum", modulus=10, weights=[3, 7, 1])
    wm = resolve_validator("weighted_modulus", spec)
    assert wm is not None and wm.name == "weighted_modulus"
    assert wm.check("011000015") is True
    assert resolve_validator("weighted_modulus", None) is None  # unparameterised → no-op
    assert resolve_validator("nope", None) is None
