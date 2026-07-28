"""
Project Workspace — 长期存储服务.

所有 ML 产物按 project-id 组织、以语义化文件名落盘。
manifest.json 是唯一索引，每次 save_step 均原子重写。

目录布局（workspace_dir / projects / <project_id> / <step> / <files>）：
  manifest.json           ← 项目索引
  input/original.png     ← 原始图
  depth/depth_map.png    ← 深度图
  depth/depth_colormap.png
  masks/objects.json     ← 所有物体的元数据
  masks/mask_<id>.png   ← 每物体二值 mask
  layers/layer_assignments.json
  layers/layer_<key>.png
  scene/scene_graph.json
  billboards/billboard_<id>.png
  multiface/<id>_face_<i>.png
  paper/paper_style_<key>.png
  paper/paper_outlined_<key>.png
  paper/paper_thickness_<key>.png
  paper/paper_thickness_gray_<key>.png
  paper/paper_normal_<key>.png
  inpaint/inpaint_<ts>_<hash>.png

v2 扩展目录：
  sequences/                           ← 序列分析结果
      <sequence_id>.json               ← SequenceResult JSON
  shots/                               ← 镜头管理
      shots_manifest.json              ← shots 索引
      <shot_id>/
          manifest.json                ← 镜头详情
          frames/
              <frame_index>.json       ← 单帧结果
              <frame_index>_depth.png  ← 深度图
          artifacts/                   ← 镜头级产物
  characters/                         ← 角色资产（三视图/变体）
      <character_id>_<asset_type>.png
      <character_id>_variation_<id>.png
  motions/                            ← 动作序列
      <character_id>_<sequence_id>.json
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from app.config import settings

# ─── Workspace root ────────────────────────────────────────────────────────────

WORKSPACE_DIR: Path = settings.workspace_dir / "projects"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


# ─── Slug helpers (剧本标题 / 角色名 / 场景名 / 动作名 → 文件夹名) ─────────────
#
# 文件夹命名新约定（v3）：
#
#   .workspace/projects/<timestamp>_<script_title>/
#       characters/<character_name>/<action_or_view>/<frame_or_file>
#       scenes/<scene_name>/<frame_or_kind>_<idx>.<ext>
#       motions/<character_name>/<action_slug>/frame_<idx>.<ext>
#       sequences/<sequence_id>.json
#       shots/<shot_id>/manifest.json
#
# 这些 slug 函数会保留 CJK 字符，只剔除跨平台文件系统不允许的字符（< > : " / \ | ? *）。
# 控制字符与首尾空白会折叠为单下划线，连续 _ 会合并。
import re as _re_slug

_INVALID_PATH_CHARS = _re_slug.compile(r'[<>:"/\\|?*\x00-\x1f]')
_COLLAPSE_RE = _re_slug.compile(r"_+")
_RESERVED_WIN_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def slugify(name: str, *, fallback: str = "unnamed", max_len: int = 80) -> str:
    """
    把任意字符串（剧本标题、角色名、场景名、动作名）转换为安全的文件夹名。

    - 保留中英文字符、数字、点、连字符
    - 剔除文件系统禁用字符 (< > : " / \\ | ? *) 与控制字符
    - 折叠连续空白与下划线
    - 长度截断到 max_len（按字符而非字节）
    - Windows 保留名 (CON/PRN/...) 追加 '_'
    """
    if name is None:
        return fallback
    s = str(name).strip()
    if not s:
        return fallback
    s = _INVALID_PATH_CHARS.sub("_", s)
    s = s.replace(" ", "_")
    s = _COLLAPSE_RE.sub("_", s)
    s = s.strip("._-")
    if not s:
        return fallback
    if len(s) > max_len:
        s = s[:max_len].rstrip("._-")
    if s.upper().split(".")[0] in _RESERVED_WIN_NAMES:
        s = s + "_"
    return s


def slugify_action(action: str | None, *, default: str = "default") -> str:
    """
    动作名（"three_view"、"walking"、"眨眼"）的 slug：
    全部小写、仅保留 [a-z0-9_\-] 与 CJK，便于作为目录名。
    """
    if not action:
        return default
    s = _INVALID_PATH_CHARS.sub("_", action.strip())
    s = _re_slug.sub(r"\s+", "_", s)
    s = _COLLAPSE_RE.sub("_", s).strip("._-")
    return s or default


def make_project_id(script_title: str | None = None) -> str:
    """
    生成项目文件夹名：<timestamp>_<slugified_title>

    title 为空时退化为纯 timestamp；同样保证路径安全。
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if script_title:
        return f"{ts}_{slugify(script_title)}"
    return ts


def frame_filename(index: int, kind: str | None = None, extension: str = "png") -> str:
    """
    帧文件命名：<kind>_<idx:03d>.<ext>  or  frame_<idx:03d>.<ext>
    """
    idx = max(0, int(index))
    if kind:
        return f"{slugify(kind, fallback='frame')}_{idx:03d}.{extension}"
    return f"frame_{idx:03d}.{extension}"


def _strip_data_url(b64: str) -> str:
    """去掉 ``data:image/png;base64,`` 前缀，返回纯 base64。"""
    if not b64:
        return ""
    if "," in b64 and b64.startswith("data:"):
        return b64.split(",", 1)[1]
    return b64


def _decode_base64_png(b64: str) -> bytes | None:
    """
    把 base64 字符串解码为 PNG bytes；空串或解码失败时返回 None。

    接受 ``data:image/png;base64,XXX`` 形式或纯 base64。
    """
    import base64 as _b64
    if not b64:
        return None
    raw = _strip_data_url(b64)
    try:
        return _b64.b64decode(raw, validate=False)
    except Exception:
        return None


# Asset payload 中可能含图片 base64 的字段名（顶层 + 字典容器内的 key）
_TOP_LEVEL_IMAGE_KEYS = {
    "reference_image", "image", "thumbnail", "anchor_image",
    "start_image", "end_image", "frame_image",
}
_IMAGE_DICT_CONTAINER_KEYS = {
    "three_view_images", "keyframe_images", "frames", "view_images",
    "keyframes",
}


def _looks_like_base64_png(s: object) -> bool:
    """
    启发式判断字符串是否是 base64 PNG：长度 > 100 且不含 ``<`` 等 XML 字符。
    """
    if not isinstance(s, str):
        return False
    raw = _strip_data_url(s)
    if len(raw) < 100:
        return False
    if "<" in raw or "{" in raw:
        return False
    return True


# 放在 ProjectStore 类之外的模块函数；ProjectStore 内的 _extract_and_save_images
# 会调用它。
def _make_image_filename(
    slot: str,
    idx: int | None = None,
    extension: str = "png",
) -> str:
    """
    生成 PNG 文件名（仅文件名，不含目录）：

    - 顶层 slot（如 ``reference_image``）： ``reference.png``
    - dict 容器内的子键（如 ``front``）： ``front.png``
    - 带 frame_index 的帧： ``front_001.png``
    """
    slot_part = slugify(slot, fallback="frame")
    if idx is not None and idx >= 0:
        return f"{slot_part}_{idx:03d}.{extension}"
    return f"{slot_part}.{extension}"

# ─── Pydantic-like dataclasses (no external deps) ───────────────────────────────


@dataclass
class ArtifactFile:
    name: str
    size: int
    sha256: str
    saved_at: str


@dataclass
class PhaseEntry:
    phase: str
    files: list[ArtifactFile]
    saved_at: str


@dataclass
class TimelineEvent:
    phase: str
    started_at: str
    finished_at: str
    duration_ms: int


@dataclass
class ProjectManifest:
    project_id: str
    shot_id: str
    created_at: str
    updated_at: str
    image_width: int
    image_height: int
    input_hash: str
    artifacts: dict[str, PhaseEntry] = field(default_factory=dict)
    timeline: list[TimelineEvent] = field(default_factory=list)
    script_data: Optional[dict] = field(default=None)
    shot_list: Optional[list] = field(default=None)

    def to_dict(self) -> dict:
        return {
            "projectId": self.project_id,
            "shotId": self.shot_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "imageWidth": self.image_width,
            "imageHeight": self.image_height,
            "inputHash": self.input_hash,
            "artifacts": {
                k: {
                    "phase": v.phase,
                    "files": [asdict(f) for f in v.files],
                    "savedAt": v.saved_at,
                }
                for k, v in self.artifacts.items()
            },
            "timeline": [asdict(t) for t in self.timeline],
            "scriptData": self.script_data,
            "shotList": self.shot_list,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProjectManifest:
        artifacts = {}
        for k, v in d.get("artifacts", {}).items():
            artifacts[k] = PhaseEntry(
                phase=k,
                files=[ArtifactFile(**f) for f in v.get("files", [])],
                saved_at=v.get("savedAt", ""),
            )
        timeline = [TimelineEvent(**t) for t in d.get("timeline", [])]
        return cls(
            project_id=d["projectId"],
            shot_id=d["shotId"],
            created_at=d["createdAt"],
            updated_at=d["updatedAt"],
            image_width=d.get("imageWidth", d.get("image_width", 0)),
            image_height=d.get("imageHeight", d.get("image_height", 0)),
            input_hash=d["inputHash"],
            artifacts=artifacts,
            timeline=timeline,
            script_data=d.get("scriptData"),
            shot_list=d.get("shotList"),
        )


@dataclass
class ProjectSummary:
    project_id: str
    shot_id: str
    created_at: str
    updated_at: str
    image_width: int
    image_height: int
    steps_completed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "projectId": self.project_id,
            "shotId": self.shot_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "imageWidth": self.image_width,
            "imageHeight": self.image_height,
            "stepsCompleted": self.steps_completed,
        }


# ─── v2: Sequence & Shot dataclasses ───────────────────────────────────────────


@dataclass
class SequenceEntry:
    """A single sequence analysis result stored in sequences/ directory."""
    sequence_id: str
    shot_id: str
    project_id: str
    created_at: str
    file: ArtifactFile

    def to_dict(self) -> dict:
        return {
            "sequenceId": self.sequence_id,
            "shotId": self.shot_id,
            "projectId": self.project_id,
            "createdAt": self.created_at,
            "file": asdict(self.file),
        }

    @classmethod
    def from_dict(cls, d: dict) -> SequenceEntry:
        return cls(
            sequence_id=d["sequenceId"],
            shot_id=d["shotId"],
            project_id=d["projectId"],
            created_at=d["createdAt"],
            file=ArtifactFile(**d["file"]),
        )


@dataclass
class SequenceSummary:
    """Lightweight summary for listing sequences."""
    sequence_id: str
    shot_id: str
    created_at: str
    frame_count: int
    objects_tracked: int
    file_size: int

    def to_dict(self) -> dict:
        return {
            "sequenceId": self.sequence_id,
            "shotId": self.shot_id,
            "createdAt": self.created_at,
            "frameCount": self.frame_count,
            "objectsTracked": self.objects_tracked,
            "fileSize": self.file_size,
        }


@dataclass
class FrameEntry:
    """A single frame stored under shots/<shot_id>/frames/."""
    frame_index: int
    frame_id: str
    frame_type: str | None
    original_url: str
    depth_url: str
    objects_count: int
    saved_at: str


@dataclass
class ShotManifest:
    """Shot-level manifest stored at shots/<shot_id>/manifest.json."""
    shot_id: str
    project_id: str
    created_at: str
    updated_at: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    frame_count: int
    description: str | None = None
    scene_type: str | None = None
    frames: list[FrameEntry] = field(default_factory=list)
    artifacts: dict[str, ArtifactFile] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "shotId": self.shot_id,
            "projectId": self.project_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "status": self.status,
            "frameCount": self.frame_count,
            "description": self.description,
            "sceneType": self.scene_type,
            "frames": [
                {
                    "frameIndex": f.frame_index,
                    "frameId": f.frame_id,
                    "frameType": f.frame_type,
                    "originalUrl": f.original_url,
                    "depthUrl": f.depth_url,
                    "objectsCount": f.objects_count,
                    "savedAt": f.saved_at,
                }
                for f in self.frames
            ],
            "artifacts": {k: asdict(v) for k, v in self.artifacts.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> ShotManifest:
        frames = [
            FrameEntry(
                frame_index=f["frameIndex"],
                frame_id=f["frameId"],
                frame_type=f.get("frameType"),
                original_url=f.get("originalUrl", ""),
                depth_url=f.get("depthUrl", ""),
                objects_count=f.get("objectsCount", 0),
                saved_at=f.get("savedAt", ""),
            )
            for f in d.get("frames", [])
        ]
        artifacts = {k: ArtifactFile(**v) for k, v in d.get("artifacts", {}).items()}
        return cls(
            shot_id=d["shotId"],
            project_id=d["projectId"],
            created_at=d.get("createdAt", ""),
            updated_at=d.get("updatedAt", ""),
            status=d.get("status", "pending"),
            frame_count=d.get("frameCount", 0),
            description=d.get("description"),
            scene_type=d.get("sceneType"),
            frames=frames,
            artifacts=artifacts,
        )


@dataclass
class ShotSummary:
    """Lightweight summary for listing shots."""
    shot_id: str
    project_id: str
    created_at: str
    updated_at: str
    status: str
    frame_count: int
    description: str | None = None
    scene_type: str | None = None

    def to_dict(self) -> dict:
        return {
            "shotId": self.shot_id,
            "projectId": self.project_id,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "status": self.status,
            "frameCount": self.frame_count,
            "description": self.description,
            "sceneType": self.scene_type,
        }


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── ProjectStore ──────────────────────────────────────────────────────────────


class ProjectStore:
    """
    项目存储服务（同步 + 异步两套 API，内部共用同一个 asyncio.Lock 字典）。

    公开 API（全部为 async）：
      create(shot_id, image_bytes, image_width, image_height)  → ProjectInfo
      save_step(project_id, step, files)                      → None
      load_artifact(project_id, step, filename)                 → bytes | dict
      list_projects()                                          → list[ProjectSummary]
      read_manifest(project_id)                                → ProjectManifest
      delete_project(project_id)                                → None
      append_timeline(project_id, event)                       → None
    """

    def __init__(self, workspace_dir: Path | None = None) -> None:
        self._workspace_dir: Path = workspace_dir if workspace_dir is not None else WORKSPACE_DIR
        self._locks: dict[str, asyncio.Lock] = {}
        # 启动时清理残留 .tmp 文件
        self._cleanup_tmp()

    # ── internal ────────────────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return self._workspace_dir / project_id

    def _step_dir(self, project_id: str, step: str) -> Path:
        return self._project_dir(project_id) / step

    def _manifest_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "manifest.json"

    def _get_lock(self, project_id: str) -> asyncio.Lock:
        if project_id not in self._locks:
            self._locks[project_id] = asyncio.Lock()
        return self._locks[project_id]

    def _cleanup_tmp(self) -> None:
        """启动时删除所有残留的 .tmp 文件，防止中断污染"""
        if not self._workspace_dir.is_dir():
            return
        for p in self._workspace_dir.rglob("*.tmp"):
            try:
                p.unlink()
            except OSError:
                pass

    # ── public async ────────────────────────────────────────────────────────────

    async def create(
        self,
        shot_id: str,
        image_bytes: bytes,
        image_width: int,
        image_height: int,
    ) -> dict:
        """
        创建新项目目录，写入原始图，生成 manifest.json。

        Returns ProjectInfo dict:
          { projectId, shotId, createdAt, inputHash }
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        project_id = f"{ts}_{shot_id}"
        proj_dir = self._project_dir(project_id)

        async with self._get_lock(project_id):
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "input").mkdir(exist_ok=True)

            # 保存原始图
            input_path = proj_dir / "input" / "original.png"
            input_path.write_bytes(image_bytes)

            # 初始化 manifest
            manifest = ProjectManifest(
                project_id=project_id,
                shot_id=shot_id,
                created_at=_now_iso(),
                updated_at=_now_iso(),
                image_width=image_width,
                image_height=image_height,
                input_hash=_sha256(image_bytes),
                artifacts={},
                timeline=[],
            )
            self._write_manifest(project_id, manifest)

        return {
            "projectId": project_id,
            "shotId": shot_id,
            "createdAt": manifest.created_at,
            "inputHash": manifest.input_hash,
        }

    async def save_step(
        self,
        project_id: str,
        step: str,
        files: dict[str, bytes | dict],
    ) -> None:
        """
        将 files 写入 <project_id>/<step>/，更新 manifest.json。

        files: { filename: bytes | dict }
          - bytes  → 写入为二进制文件（PNG 等）
          - dict   → 写入为 JSON（metadata objects.json 等）
        """
        lock = self._get_lock(project_id)
        async with lock:
            step_dir = self._step_dir(project_id, step)
            step_dir.mkdir(parents=True, exist_ok=True)

            artifact_files: list[ArtifactFile] = []

            for name, content in files.items():
                file_path = step_dir / name
                if isinstance(content, dict):
                    # JSON metadata
                    content_bytes = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
                    file_path.write_bytes(content_bytes)
                elif isinstance(content, bytes):
                    file_path.write_bytes(content)
                else:
                    raise TypeError(f"Unsupported file content type for {name}: {type(content)}")

                artifact_files.append(
                    ArtifactFile(
                        name=name,
                        size=file_path.stat().st_size,
                        sha256=_sha256(file_path.read_bytes()),
                        saved_at=_now_iso(),
                    )
                )

            # 读取并更新 manifest
            manifest = self._read_manifest(project_id)
            manifest.artifacts[step] = PhaseEntry(
                phase=step,
                files=artifact_files,
                saved_at=_now_iso(),
            )
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)

    async def load_artifact(
        self, project_id: str, step: str, filename: str
    ) -> bytes | dict:
        """读取单个产物文件。JSON 文件自动解析为 dict。"""
        file_path = self._step_dir(project_id, step) / filename
        if not file_path.is_file():
            raise FileNotFoundError(f"Artifact not found: {project_id}/{step}/{filename}")
        data = file_path.read_bytes()
        if filename.endswith(".json"):
            return json.loads(data.decode("utf-8"))
        return data

    async def list_projects(self) -> list[ProjectSummary]:
        """返回所有项目的摘要列表，按 updated_at 降序。"""
        summaries: list[ProjectSummary] = []
        if not self._workspace_dir.is_dir():
            return summaries
        for proj_dir in self._workspace_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            manifest_path = proj_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = self._read_manifest_from_path(manifest_path)
                summaries.append(
                    ProjectSummary(
                        project_id=manifest.project_id,
                        shot_id=manifest.shot_id,
                        created_at=manifest.created_at,
                        updated_at=manifest.updated_at,
                        image_width=manifest.image_width,
                        image_height=manifest.image_height,
                        steps_completed=list(manifest.artifacts.keys()),
                    )
                )
            except Exception:
                # 跳过损坏的 manifest
                continue
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    async def read_manifest(self, project_id: str) -> ProjectManifest:
        """读取项目的完整 manifest。"""
        manifest_path = self._manifest_path(project_id)
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Project not found: {project_id}")
        return self._read_manifest_from_path(manifest_path)

    async def delete_project(self, project_id: str) -> None:
        """递归删除整个项目目录。"""
        lock = self._get_lock(project_id)
        async with lock:
            proj_dir = self._project_dir(project_id)
            if proj_dir.is_dir():
                shutil.rmtree(proj_dir)
            # 清理锁引用
            self._locks.pop(project_id, None)

    async def append_timeline(
        self, project_id: str, phase: str, started_at: str, finished_at: str, duration_ms: int
    ) -> None:
        """向 timeline.json 追加一条执行记录。"""
        lock = self._get_lock(project_id)
        async with lock:
            manifest = self._read_manifest(project_id)
            manifest.timeline.append(
                TimelineEvent(
                    phase=phase,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                )
            )
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)

    # ── v2: Sequence persistence ─────────────────────────────────────────────

    def _sequences_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "sequences"

    def _sequence_file(self, project_id: str, sequence_id: str) -> Path:
        return self._sequences_dir(project_id) / f"{sequence_id}.json"

    async def save_sequence(
        self,
        project_id: str,
        sequence_data: dict[str, Any],
    ) -> SequenceEntry:
        """
        将序列分析结果持久化到 sequences/<sequence_id>.json。

        Args:
            project_id: 项目 ID
            sequence_data: SequenceResult dict (from SequenceResult.model_dump())

        Returns:
            SequenceEntry with metadata
        """
        lock = self._get_lock(project_id)
        async with lock:
            seq_dir = self._sequences_dir(project_id)
            seq_dir.mkdir(parents=True, exist_ok=True)

            sequence_id = sequence_data.get("sequenceId", f"seq_{uuid.uuid4().hex[:8]}")
            seq_path = self._sequence_file(project_id, sequence_id)

            content_bytes = json.dumps(sequence_data, ensure_ascii=False, indent=2).encode("utf-8")
            seq_path.write_bytes(content_bytes)

            entry = SequenceEntry(
                sequence_id=sequence_id,
                shot_id=sequence_data.get("shotId", ""),
                project_id=project_id,
                created_at=sequence_data.get("createdAt", _now_iso()),
                file=ArtifactFile(
                    name=f"{sequence_id}.json",
                    size=len(content_bytes),
                    sha256=_sha256(content_bytes),
                    saved_at=_now_iso(),
                ),
            )

            # Update project updated_at
            manifest = self._read_manifest(project_id)
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)

            return entry

    async def load_sequence(
        self,
        project_id: str,
        sequence_id: str,
    ) -> dict[str, Any]:
        """
        读取序列分析结果。
        """
        seq_path = self._sequence_file(project_id, sequence_id)
        if not seq_path.is_file():
            raise FileNotFoundError(f"Sequence not found: {project_id}/sequences/{sequence_id}")
        return json.loads(seq_path.read_text(encoding="utf-8"))

    async def list_sequences(
        self,
        project_id: str,
        shot_id: str | None = None,
    ) -> list[SequenceSummary]:
        """
        列出项目中的序列，按 createdAt 降序。

        Args:
            project_id: 项目 ID
            shot_id: 可选，按 shotId 过滤
        """
        seq_dir = self._sequences_dir(project_id)
        if not seq_dir.is_dir():
            return []

        summaries: list[SequenceSummary] = []
        for seq_file in sorted(seq_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(seq_file.read_text(encoding="utf-8"))
                if shot_id and data.get("shotId") != shot_id:
                    continue
                summaries.append(SequenceSummary(
                    sequence_id=data.get("sequenceId", seq_file.stem),
                    shot_id=data.get("shotId", ""),
                    created_at=data.get("createdAt", ""),
                    frame_count=data.get("frameCount", 0),
                    objects_tracked=len(data.get("crossFrameObjects", [])),
                    file_size=seq_file.stat().st_size,
                ))
            except Exception:
                continue

        return summaries

    async def delete_sequence(self, project_id: str, sequence_id: str) -> bool:
        """
        删除序列文件。
        """
        lock = self._get_lock(project_id)
        async with lock:
            seq_path = self._sequence_file(project_id, sequence_id)
            if seq_path.is_file():
                seq_path.unlink()
                return True
            return False

    # ── v2: Shot management ───────────────────────────────────────────────────

    def _shots_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "shots"

    def _shot_dir(self, project_id: str, shot_id: str) -> Path:
        return self._shots_dir(project_id) / shot_id

    def _shot_manifest_path(self, project_id: str, shot_id: str) -> Path:
        return self._shot_dir(project_id, shot_id) / "manifest.json"

    def _shot_frames_dir(self, project_id: str, shot_id: str) -> Path:
        return self._shot_dir(project_id, shot_id) / "frames"

    def _shot_artifact_dir(self, project_id: str, shot_id: str) -> Path:
        return self._shot_dir(project_id, shot_id) / "artifacts"

    def _characters_dir(self, project_id: str) -> Path:
        """
        characters/ 根目录。新布局: characters/<character_name>/<action>/<frame>。
        """
        return self._project_dir(project_id) / "characters"

    def _character_dir(
        self,
        project_id: str,
        character_name: str | None,
        action_name: str | None = None,
    ) -> Path:
        """
        角色资产目录：characters/<character_name>/<action_name>/。

        - character_name 为空时退化为 characters/_misc/<action_name>/（旧布局兼容）。
        - action_name 为空时返回 characters/<character_name>/。
        """
        chars_root = self._characters_dir(project_id)
        if not character_name:
            return chars_root / "_misc" / (slugify_action(action_name) if action_name else "")
        char_part = slugify(character_name, fallback="unnamed_character")
        if action_name:
            return chars_root / char_part / slugify_action(action_name)
        return chars_root / char_part

    def _motions_dir(self, project_id: str) -> Path:
        """
        motions/ 根目录。新布局: motions/<character_name>/<action_slug>/<frame>。
        """
        return self._project_dir(project_id) / "motions"

    def _motion_dir(
        self,
        project_id: str,
        character_name: str | None,
        action_name: str | None,
    ) -> Path:
        char_part = slugify(character_name, fallback="unnamed_character") if character_name else "_misc"
        action_part = slugify_action(action_name)
        return self._motions_dir(project_id) / char_part / action_part

    def _scenes_dir(self, project_id: str) -> Path:
        """
        scenes/ 根目录。新布局: scenes/<scene_name>/<frame>_<kind>.<ext>。
        """
        return self._project_dir(project_id) / "scenes"

    def _scene_dir(self, project_id: str, scene_name: str | None) -> Path:
        """
        场景目录：scenes/<scene_name>/。scene_name 为空时退化到 scenes/_misc/。
        """
        if not scene_name:
            return self._scenes_dir(project_id) / "_misc"
        return self._scenes_dir(project_id) / slugify(scene_name, fallback="unnamed_scene")

    async def save_scene_asset(
        self,
        project_id: str,
        scene_id: str,
        payload: Optional[dict] = None,
        *,
        asset_type: Optional[str] = None,
        file_data=None,
        extension: str = "json",
        scene_name: str | None = None,
    ) -> dict:
        """
        Save a scene asset bundle to disk.

        Calling conventions:

        1. New v3 layout (preferred):
           ``save_scene_asset(project_id, scene_id, payload=dict,
                              scene_name=...)``
           Writes ``scenes/<scene_name>/asset_<scene_id>.json``.

        2. Legacy payload-only call:
           ``save_scene_asset(project_id, scene_id, payload=dict)``
           Writes ``scenes/<scene_id>_asset.json`` (flat layout).

        3. Legacy single-file call:
           ``save_scene_asset(project_id, scene_id, asset_type,
                              file_data, extension)``
           Writes ``scenes/<scene_id>_<asset_type>.<ext>``.
        """
        lock = self._get_lock(project_id)
        async with lock:
            use_v3 = bool(scene_name)

            # ── Payload-only path (legacy or v3) ───────────────────────────────
            if payload is not None or (
                asset_type is not None
                and isinstance(asset_type, dict)
                and file_data is None
                and payload is None
            ):
                if payload is None:
                    payload = asset_type  # type: ignore[assignment]

                # 解码 payload 内的 base64 PNG → 写入独立文件，JSON 内仅存路径
                base_dir = (
                    self._scene_dir(project_id, scene_name) if use_v3 else None
                )
                payload_to_persist, _ = self._extract_and_save_images(
                    project_id, payload, base_dir=base_dir,
                )

                if use_v3:
                    scene_dir = self._scene_dir(project_id, scene_name)
                    scene_dir.mkdir(parents=True, exist_ok=True)
                    rel_path = scene_dir / f"asset_{slugify(scene_id, fallback='scene')}.json"
                else:
                    scenes_dir = self._scenes_dir(project_id)
                    scenes_dir.mkdir(parents=True, exist_ok=True)
                    rel_path = scenes_dir / f"{scene_id}_asset.json"

                abs_path = self._workspace_dir / rel_path
                import json as _json
                abs_path.write_text(
                    _json.dumps(payload_to_persist, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                # ── Single-file path ────────────────────────────────────────
                if use_v3:
                    scene_dir = self._scene_dir(project_id, scene_name)
                    scene_dir.mkdir(parents=True, exist_ok=True)
                    fname = (
                        f"{slugify(scene_id, fallback='scene')}_"
                        f"{slugify(asset_type or 'frame', fallback='frame')}.{extension}"
                    )
                    rel_path = scene_dir / fname
                else:
                    scenes_dir = self._scenes_dir(project_id)
                    scenes_dir.mkdir(parents=True, exist_ok=True)
                    rel_path = scenes_dir / f"{scene_id}_{asset_type}.{extension}"

                abs_path = self._workspace_dir / rel_path
                if isinstance(file_data, (bytes, bytearray)):
                    abs_path.write_bytes(bytes(file_data))
                elif file_data is not None:
                    abs_path.write_text(str(file_data), encoding="utf-8")
                else:
                    pass  # nothing to write

            manifest = self._read_manifest(project_id)
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)
            return {"success": True, "url": str(rel_path)}

    async def save_scene_keyframe(
        self,
        project_id: str,
        scene_id: str,
        scene_name: str | None,
        kind: str,
        file_bytes: bytes,
        extension: str = "png",
    ) -> dict:
        """
        把单个场景关键帧 (wide/closeup/mood) 写入
        scenes/<scene_name>/<scene_id>_<kind>.<ext>。
        """
        lock = self._get_lock(project_id)
        async with lock:
            scene_dir = self._scene_dir(project_id, scene_name)
            scene_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{slugify(scene_id, fallback='scene')}_{slugify(kind, fallback='frame')}.{extension}"
            rel_path = scene_dir / fname
            abs_path = self._workspace_dir / rel_path
            abs_path.write_bytes(bytes(file_bytes))

            manifest = self._read_manifest(project_id)
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)
            return {"success": True, "url": str(rel_path)}

    async def list_scene_assets(self, project_id: str) -> list[dict]:
        """List every persisted scene asset bundle for a project."""
        scenes_dir = self._scenes_dir(project_id)
        if not scenes_dir.is_dir():
            return []
        return [
            {"name": p.name, "url": str(p.relative_to(self._workspace_dir))}
            for p in sorted(scenes_dir.iterdir())
            if p.is_file()
        ]

    async def get_scene_asset(self, project_id: str, scene_id: str) -> Optional[dict]:
        """Load a single scene asset bundle. Returns None when not found."""
        scenes_dir = self._scenes_dir(project_id)
        asset_path = scenes_dir / f"{scene_id}_asset.json"
        if not asset_path.is_file():
            return None
        import json as _json
        return _json.loads(asset_path.read_text(encoding="utf-8"))

    async def create_shot(
        self,
        project_id: str,
        shot_id: str,
        description: str | None = None,
        scene_type: str | None = None,
    ) -> ShotManifest:
        """
        创建镜头目录和 manifest.json。
        """
        lock = self._get_lock(project_id)
        async with lock:
            shot_dir = self._shot_dir(project_id, shot_id)
            shot_dir.mkdir(parents=True, exist_ok=True)
            (shot_dir / "frames").mkdir(exist_ok=True)
            (shot_dir / "artifacts").mkdir(exist_ok=True)

            manifest = ShotManifest(
                shot_id=shot_id,
                project_id=project_id,
                created_at=_now_iso(),
                updated_at=_now_iso(),
                status="pending",
                frame_count=0,
                description=description,
                scene_type=scene_type,
                frames=[],
                artifacts={},
            )
            self._write_shot_manifest(project_id, shot_id, manifest)
            return manifest

    async def save_frame(
        self,
        project_id: str,
        shot_id: str,
        frame_index: int,
        frame_data: dict[str, Any],
        original_bytes: bytes | None = None,
        depth_bytes: bytes | None = None,
    ) -> None:
        """
        保存单帧结果到 shots/<shot_id>/frames/。

        Args:
            frame_data: 单帧的 FrameResult dict
            original_bytes: 可选，原始帧图像 bytes
            depth_bytes: 可选，深度图 bytes
        """
        lock = self._get_lock(project_id)
        async with lock:
            frames_dir = self._shot_frames_dir(project_id, shot_id)
            frames_dir.mkdir(parents=True, exist_ok=True)

            frame_id = frame_data.get("frameId", f"frame_{frame_index:04d}")
            idx = frame_index

            # Save frame JSON
            frame_path = frames_dir / f"{idx}.json"
            content = json.dumps(frame_data, ensure_ascii=False, indent=2).encode("utf-8")
            frame_path.write_bytes(content)

            # Save original image if provided
            if original_bytes:
                orig_path = frames_dir / f"{idx}_original.png"
                orig_path.write_bytes(original_bytes)

            # Save depth map if provided
            if depth_bytes:
                depth_path = frames_dir / f"{idx}_depth.png"
                depth_path.write_bytes(depth_bytes)

            # Update shot manifest
            manifest = self._read_shot_manifest(project_id, shot_id)
            manifest.updated_at = _now_iso()
            if manifest.status == "pending":
                manifest.status = "processing"
            self._write_shot_manifest(project_id, shot_id, manifest)

    async def load_frame(
        self,
        project_id: str,
        shot_id: str,
        frame_index: int,
    ) -> dict[str, Any]:
        """
        读取单帧结果 JSON。
        """
        frame_path = self._shot_frames_dir(project_id, shot_id) / f"{frame_index}.json"
        if not frame_path.is_file():
            raise FileNotFoundError(f"Frame not found: {project_id}/shots/{shot_id}/frames/{frame_index}.json")
        return json.loads(frame_path.read_text(encoding="utf-8"))

    async def load_frame_image(
        self,
        project_id: str,
        shot_id: str,
        frame_index: int,
        kind: Literal["original", "depth"] = "original",
    ) -> bytes:
        """
        读取帧图像（原始图或深度图）。

        Args:
            kind: "original" | "depth"
        """
        ext = "png"
        frame_path = self._shot_frames_dir(project_id, shot_id) / f"{frame_index}_{kind}.{ext}"
        if not frame_path.is_file():
            raise FileNotFoundError(f"Frame image not found: {project_id}/shots/{shot_id}/frames/{frame_index}_{kind}.{ext}")
        return frame_path.read_bytes()

    async def finalize_shot(
        self,
        project_id: str,
        shot_id: str,
        status: Literal["completed", "failed"] = "completed",
    ) -> ShotManifest:
        """
        标记镜头完成/失败，更新 frame_count。

        调用此方法应在所有帧 save_frame 完成后。
        """
        lock = self._get_lock(project_id)
        async with lock:
            frames_dir = self._shot_frames_dir(project_id, shot_id)
            json_frames = sorted(frames_dir.glob("*.json"), key=lambda p: p.stem)

            manifest = self._read_shot_manifest(project_id, shot_id)
            manifest.status = status
            manifest.frame_count = len(json_frames)
            manifest.updated_at = _now_iso()

            # Rebuild frames list from saved JSON files
            manifest.frames = []
            for frame_path in json_frames:
                idx = int(frame_path.stem)
                data = json.loads(frame_path.read_text(encoding="utf-8"))
                orig_path = frames_dir / f"{idx}_original.png"
                depth_path = frames_dir / f"{idx}_depth.png"
                manifest.frames.append(FrameEntry(
                    frame_index=idx,
                    frame_id=data.get("frameId", f"frame_{idx:04d}"),
                    frame_type=data.get("frameType"),
                    original_url=str(orig_path) if orig_path.is_file() else "",
                    depth_url=str(depth_path) if depth_path.is_file() else "",
                    objects_count=len(data.get("objects", [])),
                    saved_at=_now_iso(),
                ))

            self._write_shot_manifest(project_id, shot_id, manifest)

            # Update project manifest
            proj_manifest = self._read_manifest(project_id)
            proj_manifest.updated_at = _now_iso()
            self._write_manifest(project_id, proj_manifest)

            return manifest

    async def get_shot(self, project_id: str, shot_id: str) -> ShotManifest:
        """读取镜头 manifest。"""
        return self._read_shot_manifest(project_id, shot_id)

    async def list_shots(self, project_id: str) -> list[ShotSummary]:
        """列出项目中所有镜头。"""
        shots_dir = self._shots_dir(project_id)
        if not shots_dir.is_dir():
            return []

        summaries: list[ShotSummary] = []
        for shot_dir in sorted(shots_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not shot_dir.is_dir():
                continue
            manifest_path = shot_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                m = self._read_shot_manifest_from_path(manifest_path)
                summaries.append(ShotSummary(
                    shot_id=m.shot_id,
                    project_id=m.project_id,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                    status=m.status,
                    frame_count=m.frame_count,
                    description=m.description,
                    scene_type=m.scene_type,
                ))
            except Exception:
                continue

        return summaries

    async def delete_shot(self, project_id: str, shot_id: str) -> bool:
        """删除镜头目录。"""
        lock = self._get_lock(project_id)
        async with lock:
            shot_dir = self._shot_dir(project_id, shot_id)
            if shot_dir.is_dir():
                shutil.rmtree(shot_dir)
                return True
            return False

    # ── script / shot-list persistence ─────────────────────────────────────────

    async def save_script_data(self, project_id: str, script_data: dict) -> dict:
        """保存剧本解析结果到 manifest。"""
        lock = self._get_lock(project_id)
        async with lock:
            manifest = self._read_manifest(project_id)
            manifest.script_data = script_data
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)
            return {"success": True, "scriptData": script_data}

    async def save_characters(
        self, project_id: str, characters: list[dict]
    ) -> dict:
        """
        Save only the characters subset of script_data to manifest.

        Preserves other fields (scenes, story_paragraphs, title, etc.) if
        script_data already exists. If script_data is absent, this only
        populates the characters slice — downstream /parse calls will fill
        in the rest.
        """
        lock = self._get_lock(project_id)
        async with lock:
            manifest = self._read_manifest(project_id)
            existing = manifest.script_data or {}
            existing["characters"] = characters
            manifest.script_data = existing
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)
            return {"success": True, "characters": characters}

    async def save_shot_list(self, project_id: str, shot_list: list) -> dict:
        """保存镜头列表到 manifest。"""
        lock = self._get_lock(project_id)
        async with lock:
            manifest = self._read_manifest(project_id)
            manifest.shot_list = shot_list
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)
            return {"success": True, "shotList": shot_list}

    async def save_character_asset(
        self,
        project_id: str,
        character_id: str,
        asset_type: str = "asset",
        file_data=None,
        extension: str = "json",
        payload: Optional[dict] = None,
        *,
        character_name: str | None = None,
        action_name: str | None = None,
        frame_index: int | None = None,
    ) -> dict:
        """
        Save a character asset bundle to disk.

        Three calling conventions are supported:

        1. New v3 layout (preferred for /characters/generate-three-view and
           /characters/generate-variation):
           ``save_character_asset(project_id, character_id, payload_dict,
                                  character_name=..., action_name=...,
                                  frame_index=...)``
           Writes to ``characters/<character_name>/<action_name>/frame_<idx>.png``
           (or ``<asset_type>.json`` when payload is a dict).

        2. Legacy payload-only call:
           ``save_character_asset(project_id, character_id, payload_dict)``
           Writes to ``characters/<character_id>_asset.json`` (flat layout,
           kept for back-compat with previously persisted projects).

        3. Legacy single-file call:
           ``save_character_asset(project_id, character_id, asset_type,
                                  file_data, extension)``
           Writes ``<character_id>_<asset_type>.<ext>`` (flat layout).
        """
        lock = self._get_lock(project_id)
        async with lock:
            use_v3 = bool(character_name or action_name or frame_index is not None)

            # ── Payload-only call (covers both legacy and v3) ────────────────
            if payload is not None:
                # Extract any base64 PNGs inside the payload and write them as
                # standalone files; replace the base64 string in the persisted
                # manifest with the relative path so the JSON stays small.
                payload_to_persist, _extracted = self._extract_and_save_images(
                    project_id,
                    payload,
                    base_dir=self._character_dir(
                        project_id, character_name, action_name or "asset",
                    ) if use_v3 else None,
                )

                if use_v3:
                    char_dir = self._character_dir(
                        project_id, character_name, action_name or "asset",
                    )
                    char_dir.mkdir(parents=True, exist_ok=True)
                    fname = frame_filename(
                        frame_index or 0, kind="asset", extension="json",
                    )
                    rel_path = char_dir / fname
                else:
                    characters_dir = self._characters_dir(project_id)
                    characters_dir.mkdir(parents=True, exist_ok=True)
                    rel_path = characters_dir / f"{character_id}_asset.json"

                abs_path = self._workspace_dir / rel_path
                import json as _json
                abs_path.write_text(
                    _json.dumps(payload_to_persist, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                manifest = self._read_manifest(project_id)
                manifest.updated_at = _now_iso()
                self._write_manifest(project_id, manifest)
                return {"success": True, "url": str(rel_path)}

            # Backward-compat: ``save_character_asset(pid, cid, dict)``
            if file_data is None and isinstance(asset_type, dict):
                return await self.save_character_asset(
                    project_id,
                    character_id,
                    asset_type="asset",
                    payload=asset_type,
                    character_name=character_name,
                    action_name=action_name,
                    frame_index=frame_index,
                )

            # ── Single-file write (legacy convention) ────────────────────────
            if use_v3:
                char_dir = self._character_dir(
                    project_id, character_name, action_name or asset_type,
                )
                char_dir.mkdir(parents=True, exist_ok=True)
                fname = frame_filename(
                    frame_index or 0,
                    kind=asset_type,
                    extension=extension,
                )
                rel_path = char_dir / fname
            else:
                characters_dir = self._characters_dir(project_id)
                characters_dir.mkdir(parents=True, exist_ok=True)
                rel_path = characters_dir / f"{character_id}_{asset_type}.{extension}"

            abs_path = self._workspace_dir / rel_path
            if isinstance(file_data, (bytes, bytearray)):
                abs_path.write_bytes(bytes(file_data))
            elif file_data is not None:
                abs_path.write_text(str(file_data), encoding="utf-8")
            else:
                # No-op: nothing to write but path was reserved.
                pass

            manifest = self._read_manifest(project_id)
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)
            return {"success": True, "url": str(rel_path)}

    async def add_character_variation(
        self,
        project_id: str,
        character_id: str,
        variation_id: str,
        file_data: bytes,
        extension: str = "png",
        *,
        character_name: str | None = None,
        action_name: str | None = None,
    ) -> dict:
        """
        追加角色变体。

        新布局：characters/<character_name>/variation_<variation_id>.<ext>
        旧布局（向后兼容）：characters/<character_id>_variation_<variation_id>.<ext>
        """
        lock = self._get_lock(project_id)
        async with lock:
            if character_name or action_name:
                char_dir = self._character_dir(
                    project_id, character_name, action_name or "variation",
                )
                char_dir.mkdir(parents=True, exist_ok=True)
                rel_path = char_dir / f"variation_{slugify(variation_id, fallback='var')}.{extension}"
            else:
                characters_dir = self._characters_dir(project_id)
                characters_dir.mkdir(parents=True, exist_ok=True)
                rel_path = characters_dir / f"{character_id}_variation_{variation_id}.{extension}"

            abs_path = self._workspace_dir / rel_path
            abs_path.write_bytes(file_data)

            manifest = self._read_manifest(project_id)
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)

            return {"success": True, "url": str(rel_path)}

    async def save_motion_sequence(
        self,
        project_id: str,
        character_id: str,
        sequence_id: str,
        motion_data: dict,
        *,
        character_name: str | None = None,
        action_name: str | None = None,
        frame_index: int | None = None,
    ) -> dict:
        """
        保存角色动作序列。

        新布局：motions/<character_name>/<action_slug>/frame_<idx>.json
        旧布局（向后兼容）：motions/<character_id>_<sequence_id>.json
        """
        lock = self._get_lock(project_id)
        async with lock:
            use_v3 = bool(character_name or action_name)
            if use_v3:
                motion_dir = self._motion_dir(project_id, character_name, action_name or sequence_id)
                motion_dir.mkdir(parents=True, exist_ok=True)
                idx = frame_index if frame_index is not None else 0
                rel_path = motion_dir / f"frame_{idx:03d}.json"
            else:
                motions_dir = self._motions_dir(project_id)
                motions_dir.mkdir(parents=True, exist_ok=True)
                rel_path = motions_dir / f"{character_id}_{sequence_id}.json"

            seq_path = self._workspace_dir / rel_path
            seq_path.write_text(
                json.dumps(motion_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            manifest = self._read_manifest(project_id)
            manifest.updated_at = _now_iso()
            self._write_manifest(project_id, manifest)

            return {"success": True, "path": str(rel_path.relative_to(self._workspace_dir))}

    async def list_character_assets(self, project_id: str, character_id: str) -> list[dict]:
        """
        列出某角色的所有资产文件路径。

        同时扫描 v3 新布局 (characters/<character_name>/...) 与 v1/v2 旧布局
        (characters/<character_id>_*.*)。结果按相对路径升序返回。
        """
        characters_dir = self._characters_dir(project_id)
        if not characters_dir.is_dir():
            return []

        results: list[dict] = []
        # 1) 新布局：characters/**/<file>
        for p in sorted(characters_dir.rglob("*")):
            if p.is_file():
                # 匹配 character_id（id 或 name）作为子目录名
                parts = p.relative_to(characters_dir).parts
                if any(character_id in part for part in parts):
                    results.append({
                        "name": p.name,
                        "url": str(p.relative_to(self._workspace_dir)),
                    })
        # 2) 旧布局：characters/<character_id>_*.*
        for p in sorted(characters_dir.iterdir()):
            if p.is_file() and character_id in p.name:
                results.append({
                    "name": p.name,
                    "url": str(p.relative_to(self._workspace_dir)),
                })
        # 去重（按 url）
        seen: set[str] = set()
        unique: list[dict] = []
        for r in results:
            if r["url"] not in seen:
                seen.add(r["url"])
                unique.append(r)
        return unique

    async def list_motion_sequences(self, project_id: str, character_id: str) -> list[dict]:
        """
        列出某角色的所有动作序列 JSON。

        同时扫描 v3 新布局 (motions/<character_name>/.../*.json) 与 v1/v2 旧布局
        (motions/<character_id>_*.json)。
        """
        motions_dir = self._motions_dir(project_id)
        if not motions_dir.is_dir():
            return []

        results: list[dict] = []
        # 1) 新布局
        for p in sorted(motions_dir.rglob("*.json")):
            parts = p.relative_to(motions_dir).parts
            if any(character_id in part for part in parts):
                results.append({
                    "name": p.name,
                    "path": str(p.relative_to(self._workspace_dir)),
                })
        # 2) 旧布局
        for p in sorted(motions_dir.iterdir()):
            if p.is_file() and character_id in p.name:
                results.append({
                    "name": p.name,
                    "path": str(p.relative_to(self._workspace_dir)),
                })
        seen: set[str] = set()
        unique: list[dict] = []
        for r in results:
            if r["path"] not in seen:
                seen.add(r["path"])
                unique.append(r)
        return unique

    # ── internal sync helpers (called from within lock) ─────────────────────────

    def _extract_and_save_images(
        self,
        project_id: str,
        payload: dict,
        *,
        base_dir: Path | None = None,
    ) -> tuple[dict, list[str]]:
        """
        在 payload dict 中查找 base64 PNG 字段（顶层与 ``three_view_images`` /
        ``keyframe_images`` 等子字典容器），解码后写入独立 .png 文件，
        并把原字符串替换为相对工作区的路径。

        返回 ``(mutated_payload, list_of_relative_paths)``。

        base_dir 为空时（仅 legacy 路径），落到 ``.workspace/projects/<project_id>/_extracted/``。
        """
        if not isinstance(payload, dict):
            return payload, []

        out_dir = base_dir if base_dir is not None else self._project_dir(project_id) / "_extracted"
        out_dir.mkdir(parents=True, exist_ok=True)

        extracted: list[str] = []
        used_filenames: set[str] = set()

        def _decode_and_write(value: str, slot: str, idx: int | None) -> str | None:
            raw_bytes = _decode_base64_png(value)
            if not raw_bytes:
                return None
            fname = _make_image_filename(slot, idx)
            counter = 1
            while fname in used_filenames:
                stem, dot, ext = fname.rpartition(".")
                fname = f"{stem}_{counter}.{ext}"
                counter += 1
            used_filenames.add(fname)
            abs_path = out_dir / fname
            abs_path.write_bytes(raw_bytes)
            rel = str((out_dir / fname).relative_to(self._workspace_dir))
            extracted.append(rel)
            return rel

        def _walk(node: dict, container: str | None = None) -> None:
            for key, val in list(node.items()):
                if isinstance(val, str) and _looks_like_base64_png(val):
                    if container is None:
                        # 顶层字段
                        if key in _TOP_LEVEL_IMAGE_KEYS:
                            rel = _decode_and_write(val, key, None)
                            if rel is not None:
                                node[key] = rel
                    else:
                        # dict 容器内的键作为 slot 名（front/side/back、wide/closeup/mood…）
                        rel = _decode_and_write(val, key, None)
                        if rel is not None:
                            node[key] = rel
                elif isinstance(val, dict) and (container is None) and key in _IMAGE_DICT_CONTAINER_KEYS:
                    # 进入容器，按子键生成 filename
                    for sub_key, sub_val in list(val.items()):
                        if isinstance(sub_val, str) and _looks_like_base64_png(sub_val):
                            rel = _decode_and_write(sub_val, sub_key, None)
                            if rel is not None:
                                val[sub_key] = rel
                        elif isinstance(sub_val, list):
                            # 列表内的 frame：[{"frame_index": N, "image": b64}, ...]
                            for j, frame in enumerate(sub_val):
                                if isinstance(frame, dict):
                                    for fk, fv in list(frame.items()):
                                        if isinstance(fv, str) and _looks_like_base64_png(fv):
                                            rel = _decode_and_write(
                                                fv, sub_key, frame.get("frame_index", j),
                                            )
                                            if rel is not None:
                                                frame[fk] = rel
                elif isinstance(val, list) and container is None:
                    # 顶层 list（如 variations / frames）
                    for j, item in enumerate(val):
                        if isinstance(item, dict):
                            for fk, fv in list(item.items()):
                                if isinstance(fv, str) and _looks_like_base64_png(fv):
                                    rel = _decode_and_write(fv, key, item.get("frame_index", j))
                                    if rel is not None:
                                        item[fk] = rel
                                elif isinstance(fv, dict):
                                    # list 元素里的 dict 容器（少见，但支持）
                                    for sk, sv in list(fv.items()):
                                        if isinstance(sv, str) and _looks_like_base64_png(sv):
                                            rel = _decode_and_write(sv, sk, item.get("frame_index", j))
                                            if rel is not None:
                                                fv[sk] = rel

        _walk(payload)
        return payload, extracted

    def _write_manifest(self, project_id: str, manifest: ProjectManifest) -> None:
        """原子写入 manifest.json（写临时文件再 rename）。"""
        manifest_path = self._manifest_path(project_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # os.replace 在 Windows 上也是原子 rename
        import os as _os

        _os.replace(tmp_path, manifest_path)

    def _read_manifest(self, project_id: str) -> ProjectManifest:
        # Ensure project directory exists before reading manifest
        proj_dir = self._project_dir(project_id)
        proj_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self._manifest_path(project_id)
        if manifest_path.is_file():
            return self._read_manifest_from_path(manifest_path)
        # If manifest doesn't exist, create a default one
        manifest = ProjectManifest(
            project_id=project_id,
            shot_id="unknown",
            created_at=_now_iso(),
            updated_at=_now_iso(),
            image_width=0,
            image_height=0,
            input_hash="",
            artifacts={},
        )
        self._write_manifest(project_id, manifest)
        return manifest

    def _read_manifest_from_path(self, path: Path) -> ProjectManifest:
        # Ensure parent directory exists before reading
        path.parent.mkdir(parents=True, exist_ok=True)
        d = json.loads(path.read_text(encoding="utf-8"))
        return ProjectManifest.from_dict(d)

    # ── shot manifest helpers ──────────────────────────────────────────────────

    def _write_shot_manifest(
        self, project_id: str, shot_id: str, manifest: ShotManifest
    ) -> None:
        """原子写入 shots/<shot_id>/manifest.json（写临时文件再 rename）。"""
        manifest_path = self._shot_manifest_path(project_id, shot_id)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        import os as _os
        _os.replace(tmp_path, manifest_path)

    def _read_shot_manifest(self, project_id: str, shot_id: str) -> ShotManifest:
        return self._read_shot_manifest_from_path(self._shot_manifest_path(project_id, shot_id))

    def _read_shot_manifest_from_path(self, path: Path) -> ShotManifest:
        d = json.loads(path.read_text(encoding="utf-8"))
        return ShotManifest.from_dict(d)


# ─── Singleton ────────────────────────────────────────────────────────────────

project_store = ProjectStore(WORKSPACE_DIR)


# ─── Legacy migration ─────────────────────────────────────────────────────────


def migrate_legacy_layout(project_id: str, *, dry_run: bool = False) -> dict:
    """
    将旧版 (v1/v2) 项目目录结构迁移到 v3 (角色/动作/帧号 层级)。

    旧布局：
        characters/<char_id>_asset.json
        characters/<char_id>_variation_<vid>.png
        motions/<char_id>_<seq_id>.json
        scenes/<scene_id>_asset.json

    新布局：
        characters/<char_name>/three_view/frame_000.json
        characters/<char_name>/variation_<vid>.png
        motions/<char_name>/<action_slug>/frame_000.json
        scenes/<scene_name>/asset_<scene_id>.json

    旧布局的文件名以 ``<id>_<...>.ext`` 开头；我们把 id 段当作目录名的 fallback，
    并优先从 manifest.script_data.characters 中按 id → name 映射。

    Returns: {"moved": int, "skipped": int, "errors": [str]}
    """
    result = {"moved": 0, "skipped": 0, "errors": []}
    # 在模块作用域中使用 ``project_store`` 单例（就是 ``project_store.py`` 文件尾部的
    # ``project_store = ProjectStore(WORKSPACE_DIR)``）。注意：函数体之外已经有
    # ``from __future__ import annotations``，所以这里的引用就是模块级单例本身。
    store = project_store

    # Build id → name map from script_data
    name_map: dict[str, str] = {}
    try:
        manifest = store._read_manifest(project_id)
        if manifest.script_data:
            for ch in manifest.script_data.get("characters", []) or []:
                cid = ch.get("id") or ch.get("character_id")
                cname = ch.get("name") or ch.get("character_name")
                if cid and cname:
                    name_map[str(cid)] = str(cname)
    except Exception as e:  # pragma: no cover
        result["errors"].append(f"manifest read failed: {e}")

    def _move(src: Path, dst: Path) -> None:
        if dry_run:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            return  # already migrated
        src.rename(dst)

    # ── characters/ ────────────────────────────────────────────────────────────
    chars_dir = store._characters_dir(project_id)
    if chars_dir.is_dir():
        for f in list(chars_dir.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            stem, dot, ext = f.name.partition(".")
            if not stem:
                continue
            # <char_id>_asset.json
            if stem.endswith("_asset"):
                cid = stem[:-len("_asset")]
                name = name_map.get(cid, cid)
                dst_dir = store._character_dir(project_id, name, "three_view")
                dst = dst_dir / f"asset_000.{ext or 'json'}"
                _move(f, dst)
                result["moved"] += 1
                continue
            # <char_id>_variation_<vid>.png
            if "_variation_" in stem:
                cid, vid = stem.split("_variation_", 1)
                name = name_map.get(cid, cid)
                dst_dir = store._character_dir(project_id, name, "variation")
                dst = dst_dir / f"variation_{slugify(vid, fallback='var')}.{ext or 'png'}"
                _move(f, dst)
                result["moved"] += 1
                continue
            # <char_id>_<asset_type>.<ext> — generic
            if "_" in stem:
                cid, asset = stem.split("_", 1)
                name = name_map.get(cid, cid)
                dst_dir = store._character_dir(project_id, name, slugify_action(asset))
                dst = dst_dir / f"asset_000.{ext}"
                _move(f, dst)
                result["moved"] += 1
                continue
            result["skipped"] += 1

    # ── motions/ ───────────────────────────────────────────────────────────────
    motions_dir = store._motions_dir(project_id)
    if motions_dir.is_dir():
        for f in list(motions_dir.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            stem, dot, ext = f.name.partition(".")
            if "_" in stem:
                cid, seq = stem.split("_", 1)
                name = name_map.get(cid, cid)
                dst_dir = store._motion_dir(project_id, name, seq)
                dst = dst_dir / f"frame_000.{ext or 'json'}"
                _move(f, dst)
                result["moved"] += 1
                continue
            result["skipped"] += 1

    # ── scenes/ ────────────────────────────────────────────────────────────────
    scenes_dir = store._scenes_dir(project_id)
    if scenes_dir.is_dir():
        # Try to read scene_id → location mapping from manifest
        scene_loc_map: dict[str, str] = {}
        try:
            manifest = store._read_manifest(project_id)
            if manifest.script_data:
                for sc in manifest.script_data.get("scenes", []) or []:
                    sid = sc.get("id") or sc.get("scene_id")
                    loc = sc.get("location") or sc.get("scene_name")
                    if sid and loc:
                        scene_loc_map[str(sid)] = str(loc)
        except Exception:
            pass

        for f in list(scenes_dir.iterdir()):
            if not f.is_file() or f.name.startswith("."):
                continue
            stem, dot, ext = f.name.partition(".")
            if stem.endswith("_asset"):
                sid = stem[:-len("_asset")]
                loc = scene_loc_map.get(sid, sid)
                dst_dir = store._scene_dir(project_id, loc)
                dst = dst_dir / f"asset_{slugify(sid, fallback='scene')}.{ext or 'json'}"
                _move(f, dst)
                result["moved"] += 1
                continue
            if "_" in stem:
                sid, asset = stem.split("_", 1)
                loc = scene_loc_map.get(sid, sid)
                dst_dir = store._scene_dir(project_id, loc)
                dst = dst_dir / f"{slugify(sid, fallback='scene')}_{slugify(asset, fallback='frame')}.{ext}"
                _move(f, dst)
                result["moved"] += 1
                continue
            result["skipped"] += 1

    return result


def migrate_all_legacy_projects(*, dry_run: bool = False) -> dict:
    """
    扫描 workspace/projects 下所有项目，对每个跑一次 migrate_legacy_layout。

    Returns: {project_id: migration_result}
    """
    results: dict[str, dict] = {}
    if not WORKSPACE_DIR.is_dir():
        return results
    for proj in sorted(WORKSPACE_DIR.iterdir()):
        if not proj.is_dir():
            continue
        results[proj.name] = migrate_legacy_layout(proj.name, dry_run=dry_run)
    return results
