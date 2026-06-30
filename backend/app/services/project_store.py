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
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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


# ─── Singleton ────────────────────────────────────────────────────────────────

project_store = ProjectStore(WORKSPACE_DIR)
