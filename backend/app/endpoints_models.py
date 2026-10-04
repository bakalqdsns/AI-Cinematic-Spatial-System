"""
Model Download Management Endpoints.

Provides HTTP API for checking model download status and triggering downloads:
  GET  /api/aicss/models/status       — Return download status of all models
  POST /api/aicss/models/download/:model_name  — Trigger download of a specific model

These endpoints are primarily useful in "local" mode where models must be
downloaded and loaded locally. In "cloud" mode, only Depth and SAM2 need
to be downloaded (they have no DashScope equivalent).

Download workflow:
1. POST /download/{name}  →  HTTP 202 Accepted, worker submitted.
   The backend writes the job state to a process-wide registry.
2. GET  /status            →  Merges disk-presence with registry snapshot.
   Registry "downloading" / "error" wins over disk state so the UI can poll.
   Progress fields (bytes_done, percent, current_file, attempt) are populated
   by tqdm callbacks in the snapshot_download path or by manual reporting
   in the direct-HTTP path.
3. Frontend polls GET /status every 2 s until "downloaded" or "error".

Retry behavior:
- The endpoint wraps each download in `max_attempts` attempts with
  exponential back-off (configurable via the HF_DOWNLOAD_RETRIES env var,
  default 3). On final failure the job is marked "error" and the last
  exception is recorded.
- Per-loader retry logic (e.g. SAM2's HF Hub → Meta CDN cascade) is still
  active; the endpoint-level retry covers higher-level transient failures
  like model_manager.ensure_X raising unexpectedly.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import time
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.models.model_manager import model_manager
from app.services.download_jobs import (
    download_jobs,
    STATUS_DOWNLOADING,
    STATUS_DOWNLOADED,
    STATUS_ERROR,
)

_log = logging.getLogger("aicss")
router = APIRouter(prefix="/api/aicss/models", tags=["Models"])

# Endpoint-level retry config (independent of per-loader retries)
MAX_DOWNLOAD_ATTEMPTS = int(os.environ.get("AICSS_DOWNLOAD_RETRIES", "3"))
BACKOFF_BASE_SECONDS = 2.0  # back-off: 2s, 4s, 8s, ...


# ── Response models ────────────────────────────────────────────────────────────

class ModelDownloadItem(BaseModel):
    name: str
    model_id: str
    status: str  # "not_downloaded" | "downloaded" | "downloading" | "error"
    size_gb: float = 0.0
    path: str = ""
    # ── Progress (populated while status == "downloading") ─────────────
    progress: Optional[float] = None      # 0.0–100.0
    bytes_done: Optional[int] = None      # total bytes downloaded so far
    bytes_total: Optional[int] = None     # total bytes expected
    current_file: Optional[str] = None    # file currently being downloaded
    files_done: Optional[int] = None
    files_total: Optional[int] = None
    speed_bps: Optional[float] = None     # bytes/sec
    eta_seconds: Optional[int] = None     # seconds remaining (estimate)
    # ── Retry / error ────────────────────────────────────────────────────
    attempt: Optional[int] = None
    max_attempts: Optional[int] = None
    error_message: Optional[str] = None


class ModelStatusResponse(BaseModel):
    model_mode: str
    models: dict[str, ModelDownloadItem]


class DownloadActionResponse(BaseModel):
    success: bool
    message: str
    model: str
    max_attempts: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_eta(job_snapshot: dict) -> Optional[int]:
    """Estimate remaining seconds from elapsed time + percent."""
    started = job_snapshot.get("started_at")
    percent = job_snapshot.get("percent", 0.0)
    if not started or percent <= 0 or percent >= 100:
        return None
    elapsed = max(time.time() - started, 1.0)
    total_est = elapsed / (percent / 100.0)
    remaining = max(total_est - elapsed, 0.0)
    return int(remaining)


def _get_model_download_info() -> dict[str, ModelDownloadItem]:
    """
    Return download status for each local model that may need downloading.

    Registry state ("downloading" / "error") supersedes disk state so the UI
    can observe live progress or a failure even if disk files are absent.
    """
    disk_status = model_manager.check_models_status()
    job_snapshot = download_jobs.snapshot()

    model_map = {
        "depth": {
            "name": "DepthAnything V2",
            "model_id": settings.depth_model,
        },
        "grounding_dino": {
            "name": "Grounding DINO",
            "model_id": settings.grounding_dino_model,
        },
        "sam2": {
            "name": "SAM2",
            "model_id": f"facebook/sam2.1_{settings.sam2_model_size}",
        },
        "qwen3vl": {
            "name": "Qwen3-VL-4B",
            "model_id": settings.vlm_model,
        },
        "lama": {
            "name": "LaMa Inpainting",
            "model_id": "advimman/lama",
        },
        "image": {
            "name": "Z-Image-Turbo",
            "model_id": settings.image_model_id,
        },
    }

    result: dict[str, ModelDownloadItem] = {}
    for key, meta in model_map.items():
        disk = disk_status.get(key, {})
        disk_available = disk.get("available", False)
        disk_path = disk.get("path", "")

        # Registry state takes priority
        job = job_snapshot.get(key)
        if job and job.get("status") == STATUS_DOWNLOADING:
            result[key] = ModelDownloadItem(
                name=meta["name"],
                model_id=meta["model_id"],
                status=STATUS_DOWNLOADING,
                size_gb=0.0,
                path=disk_path,
                progress=job.get("percent"),
                bytes_done=job.get("bytes_done"),
                bytes_total=job.get("bytes_total"),
                current_file=job.get("current_file"),
                files_done=job.get("files_done"),
                files_total=job.get("files_total"),
                speed_bps=job.get("speed_bps"),
                eta_seconds=_compute_eta(job),
                attempt=job.get("attempt"),
                max_attempts=job.get("max_attempts"),
                error_message=None,
            )
            continue

        if job and job.get("status") == STATUS_ERROR:
            result[key] = ModelDownloadItem(
                name=meta["name"],
                model_id=meta["model_id"],
                status=STATUS_ERROR,
                size_gb=0.0,
                path=disk_path,
                progress=job.get("percent"),
                bytes_done=job.get("bytes_done"),
                bytes_total=job.get("bytes_total"),
                current_file=job.get("current_file"),
                files_done=job.get("files_done"),
                files_total=job.get("files_total"),
                speed_bps=None,
                eta_seconds=None,
                attempt=job.get("attempt"),
                max_attempts=job.get("max_attempts"),
                error_message=job.get("error"),
            )
            continue

        # Fall back to disk state
        result[key] = ModelDownloadItem(
            name=meta["name"],
            model_id=meta["model_id"],
            status=STATUS_DOWNLOADED if disk_available else "not_downloaded",
            size_gb=0.0,
            path=disk_path,
            progress=None,
            bytes_done=None,
            bytes_total=None,
            current_file=None,
            files_done=None,
            files_total=None,
            speed_bps=None,
            eta_seconds=None,
            attempt=None,
            max_attempts=None,
            error_message=None,
        )

    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=ModelStatusResponse)
async def models_status():
    """
    Return the download status of all models that may need local downloading.

    In cloud mode, only Depth and SAM2 require local downloads.
    In local mode, all models (Depth, SAM2, Grounding DINO, Qwen3-VL, LaMa,
    Z-Image) may need to be downloaded.
    """
    meta = model_manager.check_models_status()
    model_mode = meta.get("_meta", {}).get("model_mode", settings.model_mode)
    items = _get_model_download_info()
    return ModelStatusResponse(
        model_mode=model_mode,
        models={k: v.model_dump() for k, v in items.items()},
    )


@router.post("/download/{model_name}", response_model=DownloadActionResponse)
async def download_model(model_name: str):
    """
    Trigger download of a specific model with built-in retry.

    Supported model_name values:
      - depth
      - grounding_dino
      - sam2
      - qwen3vl
      - lama
      - image

    Returns HTTP 202 Accepted immediately; the actual download happens in a
    background thread. The endpoint-level retry wrapper re-invokes the loader
    up to `AICSS_DOWNLOAD_RETRIES` times (default 3) with exponential back-off
    if a transient failure occurs.

    To check download progress, poll GET /api/aicss/models/status.
    """
    allowed = {"depth", "grounding_dino", "sam2", "qwen3vl", "lama", "image"}
    if model_name not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {model_name}. Allowed: {sorted(allowed)}",
        )

    _log.info(
        "[models] Download requested: %s (max_attempts=%d)",
        model_name, MAX_DOWNLOAD_ATTEMPTS,
    )

    # Pre-register the job so the status endpoint shows "downloading" immediately.
    download_jobs.start(model_name, max_attempts=MAX_DOWNLOAD_ATTEMPTS)

    # Dispatch table — maps model key → (callable, label)
    dispatch = {
        "depth":          (model_manager.ensure_depth_downloaded,          "DepthAnything"),
        "grounding_dino": (model_manager.ensure_grounding_dino_downloaded, "Grounding DINO"),
        "sam2":           (model_manager.ensure_sam2_downloaded,           "SAM2"),
        "qwen3vl":        (model_manager.ensure_qwen3vl_downloaded,        "Qwen3-VL"),
        "lama":           (model_manager.ensure_lama_downloaded,           "LaMa"),
        "image":          (model_manager.ensure_z_image_downloaded,        "Z-Image"),
    }

    fn, label = dispatch[model_name]

    # ── Background worker with endpoint-level retry ────────────────────────────
    def _download_with_retry():
        last_exc: Optional[BaseException] = None
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            if attempt > 1:
                # Bump attempt counter (resets progress fields)
                download_jobs.increment_attempt(model_name)
                backoff = BACKOFF_BASE_SECONDS ** attempt
                _log.warning(
                    "[models] %s: retry %d/%d after %.1fs back-off",
                    label, attempt, MAX_DOWNLOAD_ATTEMPTS, backoff,
                )
                time.sleep(backoff)
            try:
                fn(progress_key=model_name)
                _log.info("[models] %s: download complete (attempt %d)", label, attempt)
                download_jobs.finish(model_name, STATUS_DOWNLOADED)
                return
            except Exception as exc:
                last_exc = exc
                _log.warning(
                    "[models] %s: attempt %d/%d failed: %s: %s",
                    label, attempt, MAX_DOWNLOAD_ATTEMPTS,
                    type(exc).__name__, str(exc)[:300],
                )
                # Continue to next attempt
        # All attempts exhausted
        tb = traceback.format_exception(type(last_exc), last_exc, last_exc.__traceback__)
        err_msg = (
            f"{type(last_exc).__name__}: {last_exc}\n"
            f"Last traceback:\n{''.join(tb[-3:])}"
        ) if last_exc else "Unknown error"
        _log.error("[models] %s: giving up after %d attempts", label, MAX_DOWNLOAD_ATTEMPTS)
        download_jobs.finish(model_name, STATUS_ERROR, error=err_msg)

    # Fire-and-forget in a single dedicated thread (one per request is fine —
    # we don't expect concurrent model downloads).
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix=f"dl-{model_name}",
    )
    pool.submit(_download_with_retry)

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": (
                f"Download started for {model_name}. "
                f"Poll GET /api/aicss/models/status for progress (up to "
                f"{MAX_DOWNLOAD_ATTEMPTS} attempts with exponential back-off)."
            ),
            "model": model_name,
            "max_attempts": MAX_DOWNLOAD_ATTEMPTS,
        },
    )