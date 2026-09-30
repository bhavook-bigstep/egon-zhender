"""Pure checksum validators for structured identifiers.

No logging, no I/O, no PII persisted: each validator operates only on the string
passed to it and returns a boolean. Malformed input yields ``False``, never an
exception. These are deterministic rule checks (Contract 3), suitable for
labelling a finding with a rule ID rather than a probabilistic score.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from libs.schemas import ChecksumSpec


def luhn(value: str) -> bool:
    """Validate a numeric string with the Luhn mod-10 algorithm.

    Non-digits are stripped. Requires at least two digits. Returns ``True`` iff
    the check digit is valid.
    """
    digits = [int(ch) for ch in value if ch.isdigit()]
    if len(digits) < 2:
        return False
    total = 0
    # Double every second digit from the right.
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def iban_mod97(value: str) -> bool:
    """Validate an IBAN with the ISO 13616 / ISO 7064 mod-97 check.

    Spaces are stripped and the value is uppercased. Requires length 15..34 and
    alphanumeric content. The first four characters move to the end, letters map
    A-Z -> 10..35, and the result read as an integer must be congruent to 1
    modulo 97. Any invalid input returns ``False``.
    """
    compact = value.replace(" ", "").upper()
    if not (15 <= len(compact) <= 34):
        return False
    if not compact.isalnum():
        return False
    rearranged = compact[4:] + compact[:4]
    digits = []
    for ch in rearranged:
        if ch.isdigit():
            digits.append(ch)
        elif ch.isalpha():
            digits.append(str(ord(ch) - ord("A") + 10))
        else:
            return False
    return int("".join(digits)) % 97 == 1


def aba_routing(value: str) -> bool:
    """Validate a US ABA routing number checksum.

    Non-digits are stripped. Requires exactly nine digits. Uses the repeating
    ``3, 7, 1`` weighting; the weighted sum must be divisible by ten.
    """
    digits = [int(ch) for ch in value if ch.isdigit()]
    if len(digits) != 9:
        return False
    weights = (3, 7, 1)
    total = sum(digit * weights[index % 3] for index, digit in enumerate(digits))
    return total % 10 == 0


VALIDATORS: dict[str, Callable[[str], bool]] = {
    "luhn": luhn,
    "iban_mod97": iban_mod97,
    "aba_routing": aba_routing,
}


def _compact(value: str) -> str:
    """Uppercase, alphanumeric-only view of the value (spaces/punctuation stripped)."""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _char_value(ch: str, alphabet: str) -> int | None:
    """Single-symbol value: digits → 0-9; with the `alnum` alphabet, A-Z → 10-35."""
    if ch.isdigit():
        return int(ch)
    if alphabet == "alnum" and "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    return None


def weighted_modulus(value: str, spec: ChecksumSpec) -> bool:
    """Declarative check-digit validation (no user code). See schemas.ChecksumSpec.

    `weighted_sum`: Σ(symbol_value × weight) mod m == expect, weights cycled across the
    symbols (from the left or right). Covers ABA (mod 10, [3,7,1]), ISBN-10 (mod 11), and
    many national-ID/VAT schemes. `integer`: read the value as one integer (each symbol's
    decimal expansion concatenated, optional left rotation) mod m == expect — IBAN-style.
    Any malformed input returns ``False`` rather than raising (Contract 3 discipline).
    """
    compact = _compact(value)
    if not compact:
        return False
    if spec.mode == "integer":
        rotated = compact[spec.rotate :] + compact[: spec.rotate]
        digits: list[str] = []
        for ch in rotated:
            symbol = _char_value(ch, spec.alphabet)
            if symbol is None:
                return False
            digits.append(str(symbol))
        return int("".join(digits)) % spec.modulus == spec.expect
    # weighted_sum
    values: list[int] = []
    for ch in compact:
        symbol = _char_value(ch, spec.alphabet)
        if symbol is None:
            return False
        values.append(symbol)
    weights = spec.weights
    if not weights:
        return False
    count = len(values)
    total = 0
    for index, symbol in enumerate(values):
        position = index if spec.align == "left" else (count - 1 - index)
        total += symbol * weights[position % len(weights)]
    return total % spec.modulus == spec.expect


@dataclass(frozen=True)
class ResolvedValidator:
    """A checksum ready to run: a stable name (for the finding's rule_id / reason) and the
    boolean check to apply to a matched substring."""

    name: str
    check: Callable[[str], bool]


def resolve_validator(name: str | None, spec: ChecksumSpec | None) -> ResolvedValidator | None:
    """Resolve a validator name (+ optional weighted_modulus spec) to a runnable check.
    Returns None when there is nothing to run (no validator, or a misconfigured one)."""
    if not name:
        return None
    if name == "weighted_modulus":
        if spec is None:
            return None  # declared but unparameterised → treat as no validator
        return ResolvedValidator(name, lambda value: _safe(weighted_modulus, value, spec))
    fn = VALIDATORS.get(name)
    return ResolvedValidator(name, fn) if fn is not None else None


def _safe(fn: Callable[..., bool], *args: object) -> bool:
    """Never let a checksum raise — malformed input is just an invalid identifier."""
    try:
        return bool(fn(*args))
    except Exception:
        return False


# Validator names selectable from config / the UI (named built-ins + the parameterised one).
SELECTABLE_VALIDATORS: list[str] = [*sorted(VALIDATORS), "weighted_modulus"]
