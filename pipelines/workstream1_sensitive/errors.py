"""Typed per-item pipeline errors — never a silent drop (`data-pipeline.md`).

A stage that cannot process an item raises `PipelineItemError` with an
`ExceptionCode`; the runner catches it and emits an `unable_to_process` row carrying
that code, so counts still reconcile (Contract 4).
"""

from __future__ import annotations

from libs.schemas import ExceptionCode


class PipelineItemError(Exception):
    """A recoverable, per-item failure carrying a typed exception code."""

    def __init__(self, code: ExceptionCode, message: str = "") -> None:
        self.code = code
        super().__init__(message or code.value)
