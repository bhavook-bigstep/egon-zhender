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
