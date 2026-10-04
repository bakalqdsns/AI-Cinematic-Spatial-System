"""
Download Job Registry.

Thread-safe process-wide singleton that tracks the state of each model
download job.  The backend POST /api/aicss/models/download/{name} submits a
background worker and records its progress here so the GET /status endpoint
can return meaningful "downloading" / "error" states instead of only
"downloaded" / "not_downloaded".

The registry also holds real-time progress information (bytes_done, bytes_total,
percent, current_file, attempt) so the frontend can render a progress bar and
so that retries are tracked.  huggingface_hub.snapshot_download is invoked
with a tqdm callback (see ``app.models.model_manager``) which writes directly
into this registry.
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
    """Mutable record of a single download attempt."""

    __slots__ = (
        "status",
        "started_at",
        "finished_at",
        "error",
        # Progress tracking ────────────────────────────────────────────────
        "bytes_done",
        "bytes_total",
        "percent",          # 0.0–100.0, rounded to one decimal
        "current_file",     # filename currently being downloaded (or None)
        "files_done",       # number of files completed
        "files_total",      # total files in the snapshot
        # Retry tracking ──────────────────────────────────────────────────
        "attempt",          # current attempt number (1-based)
        "max_attempts",     # cap (from endpoint)
        # ETA tracking ───────────────────────────────────────────────────
        "speed_bps",        # recent throughput in bytes/sec
        "_last_update_ts",  # monotonic timestamp of last progress tick
    )

    def __init__(self) -> None:
        self.status: str = STATUS_NOT_DOWNLOADED
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.error: Optional[str] = None

        self.bytes_done: int = 0
        self.bytes_total: int = 0
        self.percent: float = 0.0
        self.current_file: Optional[str] = None
        self.files_done: int = 0
        self.files_total: int = 0

        self.attempt: int = 0
        self.max_attempts: int = 0

        self.speed_bps: float = 0.0
        self._last_update_ts: float = 0.0

    def update_progress(
        self,
        bytes_done: Optional[int] = None,
        bytes_total: Optional[int] = None,
        current_file: Optional[str] = None,
        files_done: Optional[int] = None,
        files_total: Optional[int] = None,
    ) -> None:
        """Apply a progress update and recompute percent / speed."""
        now = time.time()
        if bytes_total is not None:
            self.bytes_total = bytes_total
        if bytes_done is not None:
            if self._last_update_ts > 0 and bytes_done > self.bytes_done:
                delta_t = now - self._last_update_ts
                if delta_t > 0.5:  # only update speed once per ~half-second
                    delta_b = bytes_done - self.bytes_done
                    self.speed_bps = delta_b / delta_t
            self.bytes_done = bytes_done
        if files_total is not None:
            self.files_total = files_total
        if files_done is not None:
            self.files_done = files_done
        if current_file is not None:
            self.current_file = current_file

        if self.bytes_total > 0:
            self.percent = round(100.0 * self.bytes_done / self.bytes_total, 1)
        elif self.files_total > 0:
            self.percent = round(100.0 * self.files_done / self.files_total, 1)
        self._last_update_ts = now


class DownloadJobs:
    """
    Per-model download job tracker.

    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, DownloadJob] = {}

    def start(self, model: str, max_attempts: int = 1) -> None:
        """Mark a model as actively downloading. Resets progress + retry counters."""
        with self._lock:
            job = self._jobs.setdefault(model, DownloadJob())
            job.status = STATUS_DOWNLOADING
            job.started_at = time.time()
            job.finished_at = None
            job.error = None
            job.bytes_done = 0
            job.bytes_total = 0
            job.percent = 0.0
            job.current_file = None
            job.files_done = 0
            job.files_total = 0
            job.attempt = 1
            job.max_attempts = max_attempts
            job.speed_bps = 0.0
            job._last_update_ts = 0.0

    def update_progress(self, model: str, **kwargs) -> None:
        """Thread-safe progress update. Pass any of bytes_done/bytes_total/
        current_file/files_done/files_total as keyword arguments."""
        with self._lock:
            job = self._jobs.get(model)
            if job is None or job.status != STATUS_DOWNLOADING:
                return
            job.update_progress(**kwargs)

    def increment_attempt(self, model: str) -> int:
        """Bump attempt counter for a retry; return the new attempt number."""
        with self._lock:
            job = self._jobs.setdefault(model, DownloadJob())
            job.attempt += 1
            # Reset progress between attempts but keep totals so ETA stays useful.
            job.bytes_done = 0
            job.percent = 0.0
            job.current_file = None
            job.files_done = 0
            job.speed_bps = 0.0
            job._last_update_ts = 0.0
            return job.attempt

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
            if status == STATUS_DOWNLOADED:
                # mark 100% so UI doesn't flicker
                job.percent = 100.0

    def snapshot(self) -> dict[str, dict]:
        """
        Return a deep copy of all job records.

        Returns:
            {model_name: {
                "status": str,
                "started_at": float|None,
                "finished_at": float|None,
                "error": str|None,
                "bytes_done": int,
                "bytes_total": int,
                "percent": float,
                "current_file": str|None,
                "files_done": int,
                "files_total": int,
                "attempt": int,
                "max_attempts": int,
                "speed_bps": float,
            }}
        """
        with self._lock:
            return {
                k: {
                    "status": v.status,
                    "started_at": v.started_at,
                    "finished_at": v.finished_at,
                    "error": v.error,
                    "bytes_done": v.bytes_done,
                    "bytes_total": v.bytes_total,
                    "percent": v.percent,
                    "current_file": v.current_file,
                    "files_done": v.files_done,
                    "files_total": v.files_total,
                    "attempt": v.attempt,
                    "max_attempts": v.max_attempts,
                    "speed_bps": round(v.speed_bps, 1),
                }
                for k, v in self._jobs.items()
            }

    def clear(self, model: str) -> None:
        """Remove a job record (used after disk-state supersedes the job record)."""
        with self._lock:
            self._jobs.pop(model, None)


# Module-level singleton — imported throughout the app
download_jobs = DownloadJobs()