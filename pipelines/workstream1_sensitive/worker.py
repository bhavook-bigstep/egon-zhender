"""Background worker thread — drains the SQLite job queue.

Claims QUEUED jobs (atomic, via the registry) and runs them through the JobService.
Fail-loud: an unexpected error marks that job FAILED and the worker continues (never
dies silently). This is the in-process PoC worker; production swaps in Celery workers.
"""

from __future__ import annotations

import logging
import threading

from libs.jobs import JobStatus
from libs.registry import JobRegistry
from pipelines.workstream1_sensitive.job_service import JobService

logger = logging.getLogger("ws1.worker")


class Worker(threading.Thread):
    def __init__(
        self, service: JobService, registry: JobRegistry, poll_seconds: float = 0.25
    ) -> None:
        super().__init__(daemon=True)
        self._service = service
        self._registry = registry
        self._poll = poll_seconds
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._registry.claim_next()
            except Exception:  # a transient claim error must not kill the worker
                logger.exception("claim_next failed; retrying after poll interval")
                self._stop.wait(self._poll)
                continue
            if job is None:
                self._stop.wait(self._poll)
                continue
            try:
                self._service.execute(job)
            except Exception:  # never kill the worker; record and continue (fail loud)
                current = self._registry.get(job.job_id) or job
                current.status = JobStatus.FAILED
                current.exception = "worker execution error"
                self._registry.update(current)
                logger.exception("job %s failed in worker", job.job_id)

    def stop(self) -> None:
        self._stop.set()
