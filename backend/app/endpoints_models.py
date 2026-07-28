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
3. Frontend polls GET /status every 2 s until "downloaded" or "error".
"""
from __future__ import annotations

import concurrent.futures
import logging
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

# ── Response models ────────────────────────────────────────────────────────────

class ModelDownloadItem(BaseModel):
    name: str
    model_id: str
    status: str  # "not_downloaded" | "downloaded" | "downloading" | "error"
    size_gb: float
    path: str
    progress: Optional[float] = None      # 0.0–1.0 (informational, loader-dependent)
    error_message: Optional[str] = None   # populated when status == "error"


class ModelStatusResponse(BaseModel):
    model_mode: str
    models: dict[str, ModelDownloadItem]


class DownloadActionResponse(BaseModel):
    success: bool
    message: str
    model: str


# ── Helpers ───────────────────────────────────────────────────────────────────

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

    result = {}
    for key, meta in model_map.items():
        disk = disk_status.get(key, {})
        disk_available = disk.get("available", False)
        disk_path = disk.get("path", "")

        # Registry state takes priority
        job = job_snapshot.get(key)
        if job:
            job_status = job["status"]
            if job_status == STATUS_DOWNLOADING:
                result[key] = ModelDownloadItem(
                    name=meta["name"],
                    model_id=meta["model_id"],
                    status=STATUS_DOWNLOADING,
                    size_gb=0.0,
                    path=disk_path,
                    progress=0.0,
                    error_message=None,
                )
                continue
            elif job_status == STATUS_ERROR:
                result[key] = ModelDownloadItem(
                    name=meta["name"],
                    model_id=meta["model_id"],
                    status=STATUS_ERROR,
                    size_gb=0.0,
                    path=disk_path,
                    progress=None,
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
    Trigger download of a specific model.

    Supported model_name values:
      - depth
      - grounding_dino
      - sam2
      - qwen3vl
      - lama
      - image

    This endpoint returns HTTP 202 Accepted immediately; the actual download
    happens in a background thread. For large models (Qwen3-VL ~8GB, Z-Image ~33GB,
    SAM2 ~2.4GB) the download may take several minutes.

    To check download progress, poll GET /api/aicss/models/status.
    """
    allowed = {"depth", "grounding_dino", "sam2", "qwen3vl", "lama", "image"}
    if model_name not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model: {model_name}. Allowed: {sorted(allowed)}",
        )

    _log.info("[models] Download requested for: %s", model_name)

    # Record that a job has started
    download_jobs.start(model_name)

    # ── Download-only worker (no GPU) ─────────────────────────────────────────
    def _download():
        try:
            if model_name == "depth":
                model_manager.ensure_depth_downloaded()
            elif model_name == "grounding_dino":
                model_manager.ensure_grounding_dino_downloaded()
            elif model_name == "sam2":
                model_manager.ensure_sam2_downloaded()
            elif model_name == "qwen3vl":
                model_manager.ensure_qwen3vl_downloaded()
            elif model_name == "lama":
                model_manager.ensure_lama_downloaded()
            elif model_name == "image":
                model_manager.ensure_z_image_downloaded()
            _log.info("[models] Download complete for: %s", model_name)
            download_jobs.finish(model_name, STATUS_DOWNLOADED)
        except Exception as e:
            _log.error("[models] Download failed for %s: %s", model_name, e)
            download_jobs.finish(model_name, STATUS_ERROR, error=str(e))

    # Fire-and-forget in a background thread
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    pool.submit(_download)

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "message": f"Download started for {model_name}. Poll GET /api/aicss/models/status for progress.",
            "model": model_name,
        },
    )
