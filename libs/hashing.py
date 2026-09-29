"""Content hashing shared across stages and adapters (port-neutral).

Kept out of any concrete source adapter so pipeline stages depend on this util, not
on a specific reader implementation.
"""

from __future__ import annotations

import hashlib
import hmac


def sha256_hex(data: bytes) -> str:
    """Return the hex SHA-256 of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_identifier(value: str, key: bytes) -> str:
    """Keyed (HMAC-SHA-256) pseudonym for an identifier — EZ-held key, before transfer.

    The key prevents dictionary attacks; only the key holder can re-identify
    (Contract 2 / `.claude/rules/privacy-sensitive-data.md`).
    """
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
