"""
Project Workspace API endpoints.

管理长期存储中的"项目"：
  POST   /api/aicss/projects              — 创建项目，提交原始图
  GET    /api/aicss/projects              — 列出所有项目（summary）
  GET    /api/aicss/projects/{pid}/manifest — 读取完整 manifest.json
  GET    /api/aicss/projects/{pid}/artifacts/{step}/{filename} — 拉取单个 PNG/JSON
  POST   /api/aicss/projects/{pid}/checkpoint — 记录断点
  DELETE /api/aicss/projects/{pid}         — 删除整个项目

既有端点（如 /analyze、/paper-layer 等）支持可选的 `projectId` 参数，
当传入时，调用完成后会自动将产物写入该项目的对应子目录。
"""

import io
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from app.services.project_store import project_store

_log = logging.getLogger("aicss")

router = APIRouter()

# 防止路径穿越：仅允许字母数字、下划线、点、横线
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


# ─── Request / Response Models ────────────────────────────────────────────────

class CheckpointRequest(BaseModel):
    phase: str
    startedAt: str
    finishedAt: str
    durationMs: int


class ProjectInfoResponse(BaseModel):
    projectId: str
    shotId: str
    createdAt: str
    inputHash: str
    imageWidth: Optional[int] = None
    imageHeight: Optional[int] = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_safe(name: str, kind: str = "name") -> str:
    """防止路径穿越：拒绝任何非安全字符"""
    if not name or not _SAFE_NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {kind} '{name}': only letters, digits, underscore, dot, dash allowed",
        )
    return name


def _pil_to_png_bytes(pil_image) -> bytes:
    """Convert PIL Image to PNG bytes without importing PIL at module level."""
    from PIL import Image
    buf = io.BytesIO()
    if pil_image.mode not in ("RGB", "RGBA", "L"):
        pil_image = pil_image.convert("RGBA")
    pil_image.save(buf, format="PNG")
    return buf.getvalue()


def _base64_to_pil(data_url: str):
    """Decode base64 data URL to PIL Image."""
    from PIL import Image
    import base64
    if data_url.startswith("data:"):
        data_url = data_url.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(data_url)))


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectInfoResponse)
async def create_project(
    shotId: str = Form(...),
    image: UploadFile = File(...),
    imageWidth: Optional[int] = Form(None),
    imageHeight: Optional[int] = Form(None),
):
    """
    创建一个新项目目录，并把上传的原始图写入 input/original.png。

    Accepts multipart/form-data:
      - shotId:  e.g. "shot_001"
      - image:   the original image (PNG/JPEG)
      - imageWidth / imageHeight: optional, will be inferred from image if not provided
    """
    if not shotId.strip():
        raise HTTPException(status_code=400, detail="shotId cannot be empty")

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty image upload")

    # Try to decode to get dimensions
    w, h = imageWidth or 0, imageHeight or 0
    if w == 0 or h == 0:
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                w, h = im.size
        except Exception:
            w, h = 1920, 1080  # default fallback

    info = await project_store.create(shotId.strip(), raw, w, h)
    return ProjectInfoResponse(
        projectId=info["projectId"],
        shotId=info["shotId"],
        createdAt=info["createdAt"],
        inputHash=info["inputHash"],
        imageWidth=w,
        imageHeight=h,
    )


@router.post("/projects/json", response_model=ProjectInfoResponse)
async def create_project_json(payload: dict):
    """
    接受 JSON 形式创建项目（用于前端发送 base64 data URL）。

    Body:
      {
        "shotId": "shot_001",
        "imageBase64": "data:image/png;base64,...",
        "imageWidth": 1920,
        "imageHeight": 1080
      }
    """
    shot_id = (payload.get("shotId") or "").strip()
    if not shot_id:
        raise HTTPException(status_code=400, detail="shotId cannot be empty")

    img_b64 = payload.get("imageBase64") or ""
    if not img_b64:
        raise HTTPException(status_code=400, detail="imageBase64 cannot be empty")

    try:
        import base64
        from PIL import Image
        if img_b64.startswith("data:"):
            raw_b64 = img_b64.split(",", 1)[1]
        else:
            raw_b64 = img_b64
        raw = base64.b64decode(raw_b64)
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode image: {e}")

    info = await project_store.create(shot_id, raw, w, h)
    return ProjectInfoResponse(
        projectId=info["projectId"],
        shotId=info["shotId"],
        createdAt=info["createdAt"],
        inputHash=info["inputHash"],
        imageWidth=w,
        imageHeight=h,
    )


@router.get("/projects")
async def list_projects():
    """列出所有项目（仅 manifest summary），按 updated_at 降序。"""
    summaries = await project_store.list_projects()
    return {
        "count": len(summaries),
        "projects": [s.to_dict() for s in summaries],
    }


@router.get("/projects/{project_id}/manifest")
async def get_manifest(project_id: str):
    """读取指定项目的完整 manifest.json。"""
    try:
        manifest = await project_store.read_manifest(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return manifest.to_dict()


@router.get("/projects/{project_id}/artifacts/{step}/{filename}")
async def get_artifact(project_id: str, step: str, filename: str):
    """拉取单个产物文件。JSON 文件自动以 application/json 返回。"""
    _validate_safe(step, "step")
    _validate_safe(filename, "filename")

    try:
        data = await project_store.load_artifact(project_id, step, filename)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact not found: {project_id}/{step}/{filename}",
        )

    if isinstance(data, dict):
        return JSONResponse(data)
    if filename.endswith(".png"):
        media_type = "image/png"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        media_type = "image/jpeg"
    else:
        media_type = "application/octet-stream"
    return Response(content=data, media_type=media_type)


@router.post("/projects/{project_id}/checkpoint")
async def post_checkpoint(project_id: str, body: CheckpointRequest):
    """记录一条断点 / 阶段完成事件到 manifest 的 timeline。"""
    try:
        await project_store.append_timeline(
            project_id,
            phase=body.phase,
            started_at=body.startedAt,
            finished_at=body.finishedAt,
            duration_ms=body.durationMs,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return {"ok": True, "projectId": project_id, "phase": body.phase}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """删除整个项目目录（不可恢复）。"""
    proj_dir = project_store._project_dir(project_id)
    if not proj_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    await project_store.delete_project(project_id)
    return {"ok": True, "projectId": project_id, "deleted": True}
