"""ReviewStore — append-only human-review / adjudication store (SQLite).

Records reviewer decisions over WS-1 findings; it is READ-ONLY w.r.t. the source
corpus and never touches a Prince Houston or Zendai record (Contract 1). Two tables:
`reviews` holds the current decision per source_id (upserted), `review_events` is an
append-only audit trail (one row per `set_decision` call, never updated or deleted) so
every adjudication is explainable and reconstructable (Contract 3).

Rows are METADATA + reviewer-supplied rationale only — no document content or raw
identifiers are handled here (`.claude/rules/privacy-sensitive-data.md`). Mirrors the
SQLite conventions in `libs/registry.py`: one connection (check_same_thread=False), a
write lock, WAL + busy_timeout, tables created on init.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

VALID_STATUSES = ("pending", "accepted", "rejected", "needs_info")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ReviewStore:
    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._lock = threading.Lock()
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                source_id TEXT PRIMARY KEY,
                job_id TEXT,
                status TEXT,
                reviewer TEXT,
                rationale TEXT,
                calibrated_score REAL,
                decided_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT,
                job_id TEXT,
                status TEXT,
                reviewer TEXT,
                rationale TEXT,
                decided_at TEXT
            )
            """
        )
        self._conn.commit()

    # --- writes ---

    def set_decision(
        self,
        source_id: str,
        job_id: str,
        status: str,
        reviewer: str,
        rationale: str = "",
        calibrated_score: float | None = None,
    ) -> dict:
        """Upsert the current review row and append one audit event; return the row.

        `status` must be one of VALID_STATUSES (else ValueError). Every call appends a
        row to `review_events` (append-only trail), so two decisions on the same
        source_id leave 2 events but 1 current `reviews` row (the latest).
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {status!r}; expected one of {VALID_STATUSES}"
            )
        decided_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO reviews (source_id, job_id, status, reviewer, rationale, "
                "calibrated_score, decided_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "job_id=excluded.job_id, status=excluded.status, reviewer=excluded.reviewer, "
                "rationale=excluded.rationale, calibrated_score=excluded.calibrated_score, "
                "decided_at=excluded.decided_at",
                (source_id, job_id, status, reviewer, rationale, calibrated_score, decided_at),
            )
            self._conn.execute(
                "INSERT INTO review_events (source_id, job_id, status, reviewer, rationale, "
                "decided_at) VALUES (?,?,?,?,?,?)",
                (source_id, job_id, status, reviewer, rationale, decided_at),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM reviews WHERE source_id=?", (source_id,)
            ).fetchone()
        return dict(row)

    # --- reads ---

    def get(self, source_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM reviews WHERE source_id=?", (source_id,)
            ).fetchone()
        return dict(row) if row else None

    def all(self) -> dict[str, dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM reviews").fetchall()
        return {row["source_id"]: dict(row) for row in rows}

    def events(self, source_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM review_events"
        params: tuple[object, ...] = ()
        if source_id is not None:
            query += " WHERE source_id=?"
            params = (source_id,)
        query += " ORDER BY id DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
