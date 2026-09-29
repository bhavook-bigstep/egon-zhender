"""JobRegistry — durable, pollable job store that doubles as the job queue (SQLite).

WAL mode + a write lock make a single-node registry safe for the API thread + the worker
thread. `claim_next()` atomically moves one QUEUED job to RUNNING (the queue). This is the
`QueueBackend` seam: production swaps SQLite for Redis/Celery + Postgres without changing
callers. Rows are METADATA ONLY — never document content or raw identifiers
(`.claude/rules/privacy-sensitive-data.md`).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from libs.jobs import Job, JobStatus, MigrationSummary

_ACTIVE = (JobStatus.QUEUED.value, JobStatus.RUNNING.value, JobStatus.RETRYING.value)
# Terminal states that may carry finalised (partial) counts — cancelled/failed jobs
# still reconcile over what they processed, so their counts roll up too.
_TERMINAL_PROCESSED = (
    JobStatus.COMPLETED.value,
    JobStatus.CANCELLED.value,
    JobStatus.FAILED.value,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobRegistry:
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
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                job_type TEXT NOT NULL,
                run_id TEXT,
                config_version TEXT,
                progress_done INTEGER DEFAULT 0,
                progress_total INTEGER DEFAULT 0,
                flagged INTEGER DEFAULT 0,
                not_flagged INTEGER DEFAULT 0,
                unable INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # --- writes ---

    def create(self, job: Job) -> Job:
        job.created_at = job.created_at or _now()
        job.updated_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (job_id, status, job_type, run_id, config_version, "
                "progress_done, progress_total, flagged, not_flagged, unable, "
                "created_at, updated_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                self._columns(job),
            )
            self._conn.commit()
        return job

    def upsert(self, job: Job) -> Job:
        """Insert the job, or replace an existing row with the same job_id.

        The interactive path uses a deterministic job_id (= f(source_id, config, seed)),
        so re-running the same item must overwrite the prior record rather than raise on
        the PRIMARY KEY. Re-runs are idempotent (same run_id, namespaced output), so the
        replacement is the same job re-materialised.
        """
        job.created_at = job.created_at or _now()
        job.updated_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (job_id, status, job_type, run_id, config_version, "
                "progress_done, progress_total, flagged, not_flagged, unable, "
                "created_at, updated_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET "
                "status=excluded.status, job_type=excluded.job_type, run_id=excluded.run_id, "
                "config_version=excluded.config_version, progress_done=excluded.progress_done, "
                "progress_total=excluded.progress_total, flagged=excluded.flagged, "
                "not_flagged=excluded.not_flagged, unable=excluded.unable, "
                "updated_at=excluded.updated_at, payload=excluded.payload",
                self._columns(job),
            )
            self._conn.commit()
        return job

    def update(self, job: Job) -> Job:
        job.updated_at = _now()
        rec = job.result.reconcile if job.result else None
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status=?, job_type=?, run_id=?, config_version=?, "
                "progress_done=?, progress_total=?, flagged=?, not_flagged=?, unable=?, "
                "updated_at=?, payload=? WHERE job_id=?",
                (
                    job.status.value,
                    job.request.job_type.value,
                    job.run_id,
                    job.request.config_version,
                    job.progress_done,
                    job.progress_total,
                    rec.flagged if rec else 0,
                    rec.not_flagged if rec else 0,
                    rec.unable_to_process if rec else 0,
                    job.updated_at,
                    job.model_dump_json(),
                    job.job_id,
                ),
            )
            self._conn.commit()
        return job

    def claim_next(self) -> Job | None:
        """Atomically move one QUEUED job to RUNNING and return it (the queue)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE status=? ORDER BY created_at LIMIT 1",
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            job = Job.model_validate_json(row["payload"])
            job.status = JobStatus.RUNNING
            job.updated_at = _now()
            self._conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, payload=? WHERE job_id=?",
                (job.status.value, job.updated_at, job.model_dump_json(), job.job_id),
            )
            self._conn.commit()
        return job

    def request_cancel(self, job_id: str) -> bool:
        """Atomically set the cancel flag (read-modify-write under ONE lock)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                return False
            job = Job.model_validate_json(row["payload"])
            if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                return False
            job.cancel_requested = True
            job.updated_at = _now()
            self._conn.execute(
                "UPDATE jobs SET updated_at=?, payload=? WHERE job_id=?",
                (job.updated_at, job.model_dump_json(), job_id),
            )
            self._conn.commit()
        return True

    def increment_progress(self, job_id: str, delta: int = 1) -> None:
        """Atomically bump progress_done (read-modify-write under ONE lock).

        Kept atomic so a concurrent request_cancel is never lost to a progress write.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                return
            job = Job.model_validate_json(row["payload"])
            job.progress_done += delta
            job.updated_at = _now()
            self._conn.execute(
                "UPDATE jobs SET progress_done=?, updated_at=?, payload=? WHERE job_id=?",
                (job.progress_done, job.updated_at, job.model_dump_json(), job_id),
            )
            self._conn.commit()

    # --- reads ---

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return Job.model_validate_json(row["payload"]) if row else None

    def list(self, limit: int = 100, status: JobStatus | None = None) -> list[Job]:
        query = "SELECT payload FROM jobs"
        params: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status=?"
            params = (status.value,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [Job.model_validate_json(r["payload"]) for r in rows]

    def migration_summary(self, authorised: int) -> MigrationSummary:
        with self._lock:
            agg = self._conn.execute(
                "SELECT COALESCE(SUM(flagged),0) f, COALESCE(SUM(not_flagged),0) n, "
                f"COALESCE(SUM(unable),0) u FROM jobs "
                f"WHERE status IN ({','.join('?' * len(_TERMINAL_PROCESSED))})",
                _TERMINAL_PROCESSED,
            ).fetchone()
            in_prog = self._conn.execute(
                f"SELECT COALESCE(SUM(progress_done),0) d FROM jobs "
                f"WHERE status IN ({','.join('?' * len(_ACTIVE))})",
                _ACTIVE,
            ).fetchone()
            by_status_rows = self._conn.execute(
                "SELECT status, COUNT(*) c FROM jobs GROUP BY status"
            ).fetchall()
        flagged, not_flagged, unable = agg["f"], agg["n"], agg["u"]
        processed = flagged + not_flagged + unable
        in_progress = int(in_prog["d"])
        remaining = max(0, authorised - processed - in_progress)
        by_status = {r["status"]: r["c"] for r in by_status_rows}
        # `processed` sums per-job counts, so re-running an item (e.g. an interactive
        # single run over an id a batch already covered) counts it more than once and can
        # exceed `authorised`. Distinct-item accounting would need per-run source_id sets;
        # for the PoC monitor we clamp completion to 100% (a migration is never >100% done)
        # and floor `remaining` at 0 (already done above). Raw counts are left truthful.
        pct = round(100.0 * processed / authorised, 1) if authorised else 0.0
        return MigrationSummary(
            authorised=authorised,
            processed=processed,
            flagged=flagged,
            not_flagged=not_flagged,
            unable_to_process=unable,
            in_progress=in_progress,
            remaining=remaining,
            pct_complete=min(100.0, pct),
            jobs_total=sum(by_status.values()),
            jobs_by_status=by_status,
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- helpers ---

    @staticmethod
    def _columns(job: Job) -> tuple[object, ...]:
        rec = job.result.reconcile if job.result else None
        return (
            job.job_id,
            job.status.value,
            job.request.job_type.value,
            job.run_id,
            job.request.config_version,
            job.progress_done,
            job.progress_total,
            rec.flagged if rec else 0,
            rec.not_flagged if rec else 0,
            rec.unable_to_process if rec else 0,
            job.created_at,
            job.updated_at,
            job.model_dump_json(),
        )
