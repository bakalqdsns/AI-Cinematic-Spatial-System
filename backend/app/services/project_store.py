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
from typing import Any, Literal

from app.config import settings

# ─── Workspace root ────────────────────────────────────────────────────────────

WORKSPACE_DIR: Path = settings.workspace_dir / "projects"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

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

    # ── internal sync helpers (called from within lock) ─────────────────────────

    def _write_manifest(self, project_id: str, manifest: ProjectManifest) -> None:
        """原子写入 manifest.json（写临时文件再 rename）。"""
        manifest_path = self._manifest_path(project_id)
        tmp_path = manifest_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # os.replace 在 Windows 上也是原子 rename
        import os as _os

        _os.replace(tmp_path, manifest_path)

    def _read_manifest(self, project_id: str) -> ProjectManifest:
        return self._read_manifest_from_path(self._manifest_path(project_id))

    def _read_manifest_from_path(self, path: Path) -> ProjectManifest:
        d = json.loads(path.read_text(encoding="utf-8"))
        return ProjectManifest.from_dict(d)

    # ── shot manifest helpers ──────────────────────────────────────────────────

    def _write_shot_manifest(
        self, project_id: str, shot_id: str, manifest: ShotManifest
    ) -> None:
        """原子写入 shots/<shot_id>/manifest.json（写临时文件再 rename）。"""
        manifest_path = self._shot_manifest_path(project_id, shot_id)
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
