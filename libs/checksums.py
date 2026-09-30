"""Pure checksum validators for structured identifiers.

No logging, no I/O, no PII persisted: each validator operates only on the string
passed to it and returns a boolean. Malformed input yields ``False``, never an
exception. These are deterministic rule checks (Contract 3), suitable for
labelling a finding with a rule ID rather than a probabilistic score.
"""

from __future__ import annotations

from collections.abc import Callable


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
