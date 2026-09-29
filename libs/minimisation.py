"""Data minimisation for hosted transfer (Contract 2).

Before any span crosses the boundary to a managed inference provider, replace
identifiers (email / phone / LinkedIn) with keyed-hash pseudonyms so raw identifiers
never leave the boundary. This is a control independent of the written-approval gate —
both must hold for egress. The key is the EZ-held key, referenced from the environment,
never stored in the repo.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from libs.hashing import hash_identifier

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LINKEDIN = re.compile(r"https?://(?:www\.)?linkedin\.com/[^\s]+", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")


class MinimisationKeyError(RuntimeError):
    """Raised when the hashing key is required but unavailable (fail closed)."""


def load_key(key_env: str | None) -> bytes:
    """Load the EZ-held hashing key from the named env var, or fail closed."""
    if not key_env:
        raise MinimisationKeyError(
            "hosted transfer requires inference.hash_key_env to name the EZ key env var"
        )
    value = os.environ.get(key_env)
    if not value:
        raise MinimisationKeyError(f"hashing key env var {key_env} is not set")
    return value.encode("utf-8")


def mask_identifiers(text: str, key: bytes) -> str:
    """Replace email/phone/LinkedIn identifiers with keyed-hash pseudonyms."""

    def _sub(prefix: str) -> Callable[[re.Match[str]], str]:
        def _replace(match: re.Match[str]) -> str:
            return f"<{prefix}:{hash_identifier(match.group(0), key)}>"

        return _replace

    text = _LINKEDIN.sub(_sub("linkedin"), text)
    text = _EMAIL.sub(_sub("email"), text)
    text = _PHONE.sub(_sub("phone"), text)
    return text
