"""剧本记录：projects.json、拖入的图片和人物视频。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.services.motion_extractor import extract_frames_from_video, segment_frames_sequence
from app.services.script_record import (
    missing_files,
    project_dir,
    read_record,
    resolve_rel,
    safe_token,
    write_bytes,
    write_record,
)

logger = logging.getLogger("aicss")
router = APIRouter(prefix="/api/aicss/v2", tags=["record"])


def _project_or_400(project_id: str):
    try:
        project_dir(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/projects.json")
async def get_project_record(project_id: str):
    _project_or_400(project_id)
    try:
        record = read_record(project_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="这个剧本还没有 projects.json")
    return record


@router.put("/projects/{project_id}/projects.json")
async def put_project_record(project_id: str, record: dict):
    _project_or_400(project_id)
    if not isinstance(record, dict):
        raise HTTPException(status_code=400, detail="记录必须是对象")
    try:
        return write_record(project_id, record)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/import")
async def import_project_record(record: dict):
    if not isinstance(record, dict):
        raise HTTPException(status_code=400, detail="记录必须是对象")
    project_id = str(record.get("projectId") or "")
    _project_or_400(project_id)
    try:
        stored = write_record(project_id, record)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return stored


@router.post("/projects/{project_id}/files")
async def upload_project_file(
    project_id: str,
    rel: str = Form(...),
    file: UploadFile = File(...),
):
    _project_or_400(project_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件是空的")
    try:
        saved = write_bytes(project_id, rel, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": saved}


@router.get("/projects/{project_id}/file")
async def get_project_file(project_id: str, rel: str):
    _project_or_400(project_id)
    try:
        path = resolve_rel(project_id, rel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不在这个剧本目录里")
    return FileResponse(path)


@router.post("/projects/{project_id}/shots/{shot_id}/action-video")
async def ingest_action_video(
    project_id: str,
    shot_id: str,
    character_id: str = Form(...),
    file: UploadFile = File(...),
):
    _project_or_400(project_id)
    try:
        shot_token = safe_token(shot_id)
        char_token = safe_token(character_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".webm", ".mkv"}:
        suffix = ".mp4"
    folder = f"motions/{shot_token}_{char_token}"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="视频是空的")
    video_rel = write_bytes(project_id, f"{folder}/source{suffix}", data)
    video_abs = resolve_rel(project_id, video_rel)
    frame_dir = resolve_rel(project_id, f"{folder}/frames")
    frame_dir.mkdir(parents=True, exist_ok=True)

    try:
        frames = extract_frames_from_video(str(video_abs), str(frame_dir))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not frames:
        raise HTTPException(status_code=400, detail="没有抽出帧")

    root = project_dir(project_id).resolve()
    segmented_dir = resolve_rel(project_id, f"{folder}/segmented")
    sam2_model = None
    sam_error = None
    try:
        from app.models import model_manager
        sam2_model = model_manager.sam2
    except Exception as exc:
        sam_error = str(exc)

    if sam2_model is None:
        return {
            "videoPath": video_rel,
            "frameCount": len(frames),
            "segmentedFrames": [],
            "status": "error",
            "error": sam_error or "SAM2 还没有加载，抽帧已保存，人物分割还没完成",
        }

    try:
        segmented = segment_frames_sequence(
            frames,
            str(segmented_dir),
            sam2_model,
            character_id,
            shot_id,
        )
    except Exception as exc:
        logger.exception("action video segment failed")
        return {
            "videoPath": video_rel,
            "frameCount": len(frames),
            "segmentedFrames": [],
            "status": "error",
            "error": str(exc),
        }

    rows = []
    for item in segmented:
        seg_path = Path(item.segmented_path).resolve()
        if not item.segmented_path or not seg_path.is_file():
            continue
        rel = seg_path.relative_to(root).as_posix()
        rows.append({
            "frameIndex": item.frame_index,
            "path": rel,
            "filename": seg_path.name,
        })
    if not rows:
        return {
            "videoPath": video_rel,
            "frameCount": len(frames),
            "segmentedFrames": [],
            "status": "error",
            "error": "抽帧完成，但没有得到分割结果",
        }
    return {
        "videoPath": video_rel,
        "frameCount": len(rows),
        "segmentedFrames": rows,
        "status": "done",
        "error": None,
        "missingFiles": missing_files(project_id, {"motionSequences": {"row": {"videoPath": video_rel, "segmentedFrames": rows}}}),
    }
