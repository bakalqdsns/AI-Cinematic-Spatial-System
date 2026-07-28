"""
Download Job Registry.

Thread-safe process-wide singleton that tracks the state of each model
download job.  The backend POST /api/aicss/models/download/{name} submits a
background worker and records its progress here so the GET /status endpoint
can return meaningful "downloading" / "error" states instead of only
"downloaded" / "not_downloaded".
"""
from __future__ import annotations

import threading
import time
from typing import Optional

# Allowed status values
STATUS_NOT_DOWNLOADED = "not_downloaded"
STATUS_DOWNLOADING = "downloading"
STATUS_DOWNLOADED = "downloaded"
STATUS_ERROR = "error"


class DownloadJob:
    __slots__ = ("status", "started_at", "finished_at", "error")

    def __init__(self) -> None:
        self.status: str = STATUS_NOT_DOWNLOADED
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.error: Optional[str] = None


class DownloadJobs:
    """
    Per-model download job tracker.

    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, DownloadJob] = {}

    def start(self, model: str) -> None:
        """Mark a model as actively downloading."""
        with self._lock:
            job = self._jobs.setdefault(model, DownloadJob())
            job.status = STATUS_DOWNLOADING
            job.started_at = time.time()
            job.finished_at = None
            job.error = None

    def finish(self, model: str, status: str, error: Optional[str] = None) -> None:
        """
        Record that a job reached a terminal state.

        status must be one of STATUS_DOWNLOADED or STATUS_ERROR.
        """
        with self._lock:
            job = self._jobs.setdefault(model, DownloadJob())
            job.status = status
            job.finished_at = time.time()
            job.error = error

    def snapshot(self) -> dict[str, dict]:
        """
        Return a deep copy of all job records.

        Returns:
            {model_name: {"status": str, "started_at": float|None,
                         "finished_at": float|None, "error": str|None}}
        """
        with self._lock:
            return {
                k: {
                    "status": v.status,
                    "started_at": v.started_at,
                    "finished_at": v.finished_at,
                    "error": v.error,
                }
                for k, v in self._jobs.items()
            }

    def clear(self, model: str) -> None:
        """Remove a job record (used after disk-state supersedes the job record)."""
        with self._lock:
            self._jobs.pop(model, None)


# Module-level singleton — imported throughout the app
download_jobs = DownloadJobs()
