"""Shared redaction helper (Contract 2).

Anything loggable routes through here. Free text is never emitted to logs; it is
replaced by a non-identifying, length-only placeholder. Items are referenced by
source ID and evidence location only (`.claude/rules/privacy-sensitive-data.md`).
"""

from __future__ import annotations


def redact(text: str) -> str:
    """Return a non-identifying placeholder standing in for free text."""
    return f"<redacted:{len(text)} chars>"


def safe_stage_message(source_id: str, stage: str, outcome: str) -> str:
    """Build a loggable message carrying no sensitive content."""
    return f"item={source_id} stage={stage} outcome={outcome}"
