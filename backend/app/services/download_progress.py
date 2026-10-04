"""
Download progress utilities.

Provides a tqdm-compatible progress callback for huggingface_hub.snapshot_download
plus a simple per-file progress reporter for direct HTTP downloads. Both feed
into the process-wide `download_jobs` registry so the frontend can render a
real progress bar.

Usage from a loader:

    from app.services.download_progress import make_tqdm_callback, report_file_progress

    # huggingface_hub path
    snapshot_download(
        repo_id=...,
        tqdm_class=make_tqdm_callback("depth"),
        etag_timeout=...,
    )

    # direct HTTP path (with Content-Length)
    for chunk in resp.iter_content(chunk_size=...):
        report_file_progress("sam2", filename, bytes_done, bytes_total)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.download_jobs import download_jobs

logger = logging.getLogger(__name__)


def report_file_progress(
    model: str,
    filename: Optional[str],
    bytes_done: int,
    bytes_total: int,
    files_done: Optional[int] = None,
    files_total: Optional[int] = None,
) -> None:
    """
    Push a single progress tick to the registry. Safe to call from any thread.

    bytes_total=0 → percent computed from files_done / files_total.
    """
    try:
        download_jobs.update_progress(
            model,
            bytes_done=bytes_done,
            bytes_total=bytes_total,
            current_file=filename,
            files_done=files_done,
            files_total=files_total,
        )
    except Exception as e:
        logger.debug("[download-progress] update failed: %s", e)


def make_tqdm_callback(model: str):
    """
    Build a tqdm-compatible class that feeds progress into the registry.

    huggingface_hub.snapshot_download accepts ``tqdm_class`` (an arbitrary
    class with the same interface as ``tqdm.tqdm``). We instantiate it with
    the standard kwargs it would normally receive and forward ``update`` /
    ``set_postfix`` / ``close`` to the registry.

    This intentionally does NOT print to stderr — tqdm's default output
    would clutter the log stream and slow down the download thread. The
    frontend reads progress from GET /api/aicss/models/status.
    """
    from tqdm.auto import tqdm as _tqdm

    class _RegistryTqdm(_tqdm):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("disable", True)
            super().__init__(*args, **kwargs)
            self._model = model
            self._last_files_done = 0

        def update(self, n=1):
            super().update(n)
            try:
                # tqdm tracks bytes via format_dict; fetch defensively
                fd = self.format_dict
                done = int(fd.get("n", 0))
                total = int(fd.get("total", 0)) or 0
                # refresh current_file from desc / postfix
                cf = self.desc or (self.format_dict.get("postfix", {}) or {}).get("filename")
                report_file_progress(model, cf, done, total)
            except Exception:
                pass

        def set_postfix(self, ordered_dict=None, refresh=True, **kwargs):
            super().set_postfix(ordered_dict, refresh=refresh, **kwargs)
            # huggingface_hub uses postfix={"filename": "model.safetensors"}; capture it
            try:
                pf = dict(ordered_dict or {})
                pf.update(kwargs)
                cf = pf.get("filename") or pf.get("file")
                if cf is not None:
                    report_file_progress(model, str(cf), self.format_dict.get("n", 0),
                                         self.format_dict.get("total", 0))
            except Exception:
                pass

        def close(self):
            try:
                super().close()
            except Exception:
                pass

    return _RegistryTqdm


def estimate_eta(model: str, percent: float, started_at: Optional[float]) -> Optional[int]:
    """
    Estimate seconds remaining based on elapsed time and current percent.

    Returns None if the estimate would be unreliable (started_at is None,
    percent is 0, or > 100).
    """
    if not started_at or percent <= 0 or percent >= 100:
        return None
    import time
    elapsed = max(time.time() - started_at, 1.0)
    total_est = elapsed / (percent / 100.0)
    remaining = max(total_est - elapsed, 0.0)
    return int(remaining)