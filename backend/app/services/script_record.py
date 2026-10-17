"""每个剧本一份 projects.json，文件本体留在该项目目录里。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.project_store import WORKSPACE_DIR

RECORD_NAME = "projects.json"
_MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm"}


def project_dir(project_id: str) -> Path:
    if not project_id or any(part in project_id for part in ("/", "\\", "..")):
        raise ValueError("无效的项目编号")
    return WORKSPACE_DIR / project_id


def safe_rel(rel: str) -> str:
    text = rel.replace("\\", "/").lstrip("/")
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("无效的相对路径")
    return "/".join(parts)


def resolve_rel(project_id: str, rel: str) -> Path:
    root = project_dir(project_id).resolve()
    path = (root / safe_rel(rel)).resolve()
    if path != root and root not in path.parents:
        raise ValueError("路径超出项目目录")
    return path


def _relativize(project_id: str, value: Any) -> Any:
    if isinstance(value, str):
        try:
            path = Path(value).resolve()
        except OSError:
            return value
        root = project_dir(project_id).resolve()
        if path == root or root in path.parents:
            return path.relative_to(root).as_posix()
        return value
    if isinstance(value, list):
        return [_relativize(project_id, item) for item in value]
    if isinstance(value, dict):
        return {key: _relativize(project_id, item) for key, item in value.items()}
    return value


def _attach_confirmed(project_id: str, record: dict) -> None:
    root = project_dir(project_id)
    for shot in record.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("id") or "")
        if not shot_id or ".." in shot_id or "/" in shot_id or "\\" in shot_id:
            continue
        order = root / "shots" / shot_id / "confirmed_layers" / "order.json"
        if order.is_file():
            shot["confirmedLayers"] = f"shots/{shot_id}/confirmed_layers"


def _path_fields(record: dict) -> list[str]:
    found: list[str] = []

    def take(value: Any) -> None:
        if isinstance(value, str) and value and not value.startswith(("data:", "http://", "https://", "blob:")):
            if "/" in value or "\\" in value:
                found.append(value.replace("\\", "/"))

    for asset in (record.get("characterAssets") or {}).values():
        if not isinstance(asset, dict):
            continue
        take(asset.get("referenceImage"))
        views = asset.get("threeViewImages") or {}
        if isinstance(views, dict):
            for view in views.values():
                take(view)
    for asset in (record.get("sceneAssets") or {}).values():
        if not isinstance(asset, dict):
            continue
        frames = asset.get("keyframeImages") or {}
        if isinstance(frames, dict):
            for frame in frames.values():
                take(frame)
    for motion in (record.get("motionSequences") or {}).values():
        if not isinstance(motion, dict):
            continue
        take(motion.get("videoPath"))
        for frame in motion.get("segmentedFrames") or []:
            if isinstance(frame, dict):
                take(frame.get("path"))
    for row in (record.get("progress") or {}).values():
        if isinstance(row, dict):
            take(row.get("renderPath"))
    for shot in record.get("shots") or []:
        if isinstance(shot, dict):
            take(shot.get("confirmedLayers"))
    return found


def missing_files(project_id: str, record: dict) -> list[str]:
    root = project_dir(project_id)
    missing: list[str] = []
    for rel in _path_fields(record):
        try:
            path = resolve_rel(project_id, rel)
        except ValueError:
            missing.append(rel)
            continue
        if not path.exists():
            missing.append(path.relative_to(root.resolve()).as_posix() if root.resolve() in path.parents or path == root.resolve() else rel)
    return missing


def read_record(project_id: str) -> dict | None:
    path = project_dir(project_id) / RECORD_NAME
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("projects.json 不是对象")
    data["missingFiles"] = missing_files(project_id, data)
    return data


def write_record(project_id: str, record: dict) -> dict:
    root = project_dir(project_id)
    root.mkdir(parents=True, exist_ok=True)
    stored = _relativize(project_id, dict(record))
    stored["projectId"] = project_id
    _attach_confirmed(project_id, stored)
    stored["missingFiles"] = missing_files(project_id, stored)
    target = root / RECORD_NAME
    target.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    return stored


def write_bytes(project_id: str, rel: str, data: bytes) -> str:
    path = resolve_rel(project_id, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return safe_rel(rel)


def safe_token(value: str) -> str:
    cleaned = re.sub(r"[^\w\-]", "_", value, flags=re.UNICODE).strip("_")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("无效的名称")
    return cleaned
