"""RunLedger (Part 5 / Contract 4).

Append-only record of per-stage outcomes plus run-level reconciliation. Events carry
only source IDs, stage names, outcomes, typed exception codes, and non-sensitive
numeric metrics — never document content or raw identifiers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from libs.schemas import ExceptionCode, FlagStatus, ReconcileReport


@dataclass(frozen=True)
class StageEvent:
    """One immutable stage outcome for one item.

    `detail` carries only non-sensitive, content-free metrics — counts, ratios, decisions,
    scores, taxonomy category counts — never document content or matched strings.
    """

    source_id: str
    stage: str
    outcome: str
    exception_code: ExceptionCode | None = None
    detail: dict[str, float | int | str] = field(default_factory=dict)
    # The step's per-item reasoning trace — one row per detection / routed category /
    # model result. Content-free: entity TYPES, evidence LOCATIONS, scores, decisions —
    # never the matched string, extracted text, or raw identifiers.
    records: list[dict[str, str | float | int | None]] = field(default_factory=list)


class RunLedger:
    """Append-only ledger for a single run."""

    def __init__(
        self,
        run_id: str,
        config_version: str,
        on_event: Callable[[StageEvent], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.config_version = config_version
        self._events: list[StageEvent] = []
        self._final_status: dict[str, FlagStatus] = {}
        self._on_event = on_event  # live hook (e.g. SSE for the interactive view)

    def record_stage_event(self, event: StageEvent) -> None:
        self._events.append(event)
        if self._on_event is not None:
            self._on_event(event)

    def record_final(self, source_id: str, flag_status: FlagStatus) -> None:
        self._final_status[source_id] = flag_status

    def absorb(self, other: RunLedger) -> None:
        """Merge another ledger's events + final statuses into this one.

        Used by the batch runner: each item is processed with its own local ledger
        (thread-safe, no shared mutable state), then merged here in a deterministic
        order so the combined ledger is reproducible regardless of completion order.
        """
        self._events.extend(other._events)
        self._final_status.update(other._final_status)

    @property
    def events(self) -> tuple[StageEvent, ...]:
        """Read-only view of the appended events."""
        return tuple(self._events)

    def final_statuses(self) -> dict[str, str]:
        """Deterministic map of source_id → final flag status (sorted)."""
        return {
            source_id: status.value
            for source_id, status in sorted(self._final_status.items())
        }

    def reconcile(self, input_count: int) -> ReconcileReport:
        counts = Counter(self._final_status.values())
        flagged = counts.get(FlagStatus.FLAGGED, 0)
        not_flagged = counts.get(FlagStatus.NOT_FLAGGED, 0)
        unable = counts.get(FlagStatus.UNABLE_TO_PROCESS, 0)
        total = flagged + not_flagged + unable
        one_row_per_input = len(self._final_status) == input_count
        reconciled = one_row_per_input and total == input_count
        return ReconcileReport(
            input_count=input_count,
            flagged=flagged,
            not_flagged=not_flagged,
            unable_to_process=unable,
            one_row_per_input=one_row_per_input,
            reconciled=reconciled,
        )
