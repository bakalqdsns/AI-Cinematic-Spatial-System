"""
Mesh Export Persistence Service — 单例模式，管理 3D mesh 工件的持久化。

设计原则与 ProjectStore 完全一致：
- 单例模式：整个进程共享一份实例
- per-project asyncio.Lock：避免并发写入冲突
- manifest.json 原子写入：写临时文件再 os.replace
- meshes/ 目录结构：objects/, layers/, scenes/ 三个子目录

目录结构：
    <workspace>/<project_id>/
    └── meshes/
        ├── mesh_manifest.json           ← mesh 导出索引（独立管理）
        ├── objects/
        │   ├── <object_id>.glb
        │   └── <object_id>.fbx
        ├── layers/
        │   ├── <layer_key>.glb
        │   └── <layer_key>.fbx
        └── scenes/
            ├── <scene_id>.glb
            └── <scene_id>.fbx

与 project_store.py 的区别：
- ProjectStore 管理所有 ML 工件（depth, masks, paper, etc.）
- ProjectStoreMesh 仅管理 3D mesh 导出结果
- 各自维护独立的 manifest 文件，避免耦合
"""

import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# 工作空间根目录
# ─────────────────────────────────────────────────────────────────────────────

_WS_ROOT = settings.workspace_dir / "projects"


def _now_iso() -> str:
    """返回当前 UTC 时间（ISO 8601）。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _sha256(file_bytes: bytes) -> str:
    return "sha256:" + hashlib.sha256(file_bytes).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MeshArtifactFile:
    """单个 mesh 文件的元数据（与 ArtifactFile 对齐）。"""
    name: str           # 文件名，如 "foreground.glb"
    size: int           # 字节数
    sha256: str         # SHA-256 内容哈希
    saved_at: str       # ISO 8601


@dataclass
class MeshEntry:
    """
    单个 mesh 导出条目。

    对应一个 export_*() 调用产生的单个 mesh 文件。
    """
    mesh_id: str                         # 唯一标识
    project_id: str
    scope: str                            # "object" | "layer" | "scene"
    target_id: str                        # object_id | layer_key | scene_id
    format: str                           # "glb" | "fbx"
    file_name: str                        # 存储的文件名
    file_size: int
    file_sha256: str
    object_count: int                    # mesh 中包含的对象数
    vertex_count: int
    face_count: int
    include_textures: bool
    created_at: str
    error: Optional[str] = None


@dataclass
class MeshManifest:
    """
    Mesh 导出索引。

    存储在 <project_id>/meshes/mesh_manifest.json，
    与 project_store.py 的 manifest.json 完全独立。
    """
    project_id: str
    meshes: list[MeshEntry] = field(default_factory=list)
    updated_at: str = field(default_factory=_now_iso)


# ─────────────────────────────────────────────────────────────────────────────
# ProjectStoreMesh — 单例
# ─────────────────────────────────────────────────────────────────────────────


class ProjectStoreMesh:
    _instance: Optional["ProjectStoreMesh"] = None
    _locks: dict[str, asyncio.Lock] = {}
    _locks_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __new__(cls) -> "ProjectStoreMesh":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

    # ── 目录 helpers ────────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> Path:
        return _WS_ROOT / project_id

    def _meshes_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "meshes"

    def _mesh_objects_dir(self, project_id: str) -> Path:
        return self._meshes_dir(project_id) / "objects"

    def _mesh_layers_dir(self, project_id: str) -> Path:
        return self._meshes_dir(project_id) / "layers"

    def _mesh_scenes_dir(self, project_id: str) -> Path:
        return self._meshes_dir(project_id) / "scenes"

    def _mesh_manifest_path(self, project_id: str) -> Path:
        return self._meshes_dir(project_id) / "mesh_manifest.json"

    # ── Lock management ────────────────────────────────────────────────────

    async def _get_lock(self, project_id: str) -> asyncio.Lock:
        async with self._locks_lock:
            if project_id not in self._locks:
                self._locks[project_id] = asyncio.Lock()
            return self._locks[project_id]

    # ── Manifest 读写 ────────────────────────────────────────────────────

    def _read_manifest(self, project_id: str) -> MeshManifest:
        manifest_path = self._mesh_manifest_path(project_id)
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                meshes = [MeshEntry(**m) for m in data.get("meshes", [])]
                return MeshManifest(project_id=project_id, meshes=meshes)
            except (json.JSONDecodeError, TypeError):
                pass
        return MeshManifest(project_id=project_id)

    def _write_manifest(self, project_id: str, manifest: MeshManifest) -> None:
        manifest.updated_at = _now_iso()
        manifest_path = self._mesh_manifest_path(project_id)
        tmp_path = manifest_path.with_suffix(".json.tmp")

        data = {
            "projectId": manifest.project_id,
            "meshes": [
                {
                    "mesh_id": m.mesh_id,
                    "project_id": m.project_id,
                    "scope": m.scope,
                    "target_id": m.target_id,
                    "format": m.format,
                    "file_name": m.file_name,
                    "file_size": m.file_size,
                    "file_sha256": m.file_sha256,
                    "object_count": m.object_count,
                    "vertex_count": m.vertex_count,
                    "face_count": m.face_count,
                    "include_textures": m.include_textures,
                    "created_at": m.created_at,
                    "error": m.error,
                }
                for m in manifest.meshes
            ],
            "updated_at": manifest.updated_at,
        }

        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, manifest_path)

    # ── 保存 mesh 文件 ────────────────────────────────────────────────────

    async def save_mesh(
        self,
        project_id: str,
        mesh_data: bytes,
        scope: str,
        target_id: str,
        format: str,
        metadata: dict,
    ) -> MeshEntry:
        """
        保存一个 3D mesh 文件到项目目录。

        Args:
            project_id: 项目 ID
            mesh_data: mesh 文件的二进制内容（GLB/FBX）
            scope: "object" | "layer" | "scene"
            target_id: 对象 ID / 层名 / 场景 ID
            format: "glb" | "fbx"
            metadata: 导出元数据 { object_count, vertex_count, face_count, include_textures }

        Returns:
            MeshEntry: 已保存条目的元数据
        """
        lock = await self._get_lock(project_id)
        async with lock:
            # 确定目录
            if scope == "object":
                sub_dir = self._mesh_objects_dir(project_id)
            elif scope == "layer":
                sub_dir = self._mesh_layers_dir(project_id)
            else:
                sub_dir = self._mesh_scenes_dir(project_id)

            sub_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名和 mesh_id
            mesh_id = f"mesh-{uuid.uuid4().hex[:8]}"
            safe_target = _sanitize(target_id)
            file_name = f"{safe_target}.{format}"
            file_path = sub_dir / file_name

            # 避免文件名冲突：同名时加序号
            counter = 1
            while file_path.exists():
                file_name = f"{safe_target}_{counter}.{format}"
                file_path = sub_dir / file_name
                counter += 1

            # 写入文件
            file_path.write_bytes(mesh_data)
            file_size = file_path.stat().st_size
            sha256_str = _sha256(file_path.read_bytes())

            # 构建条目
            entry = MeshEntry(
                mesh_id=mesh_id,
                project_id=project_id,
                scope=scope,
                target_id=target_id,
                format=format,
                file_name=file_name,
                file_size=file_size,
                file_sha256=sha256_str,
                object_count=metadata.get("object_count", 0),
                vertex_count=metadata.get("vertex_count", 0),
                face_count=metadata.get("face_count", 0),
                include_textures=metadata.get("include_textures", True),
                created_at=_now_iso(),
                error=metadata.get("error"),
            )

            # 更新 manifest
            manifest = self._read_manifest(project_id)
            manifest.meshes.append(entry)
            self._write_manifest(project_id, manifest)

            return entry

    async def save_object_mesh(
        self,
        project_id: str,
        object_id: str,
        mesh_data: bytes,
        format: str,
        object_count: int = 1,
        vertex_count: int = 0,
        face_count: int = 0,
        include_textures: bool = True,
        error: Optional[str] = None,
    ) -> MeshEntry:
        """保存对象级 mesh（单个物体）。"""
        return await self.save_mesh(
            project_id=project_id,
            mesh_data=mesh_data,
            scope="object",
            target_id=object_id,
            format=format,
            metadata={
                "object_count": object_count,
                "vertex_count": vertex_count,
                "face_count": face_count,
                "include_textures": include_textures,
                "error": error,
            },
        )

    async def save_layer_mesh(
        self,
        project_id: str,
        layer_key: str,
        mesh_data: bytes,
        format: str,
        object_count: int = 0,
        vertex_count: int = 0,
        face_count: int = 0,
        include_textures: bool = True,
        error: Optional[str] = None,
    ) -> MeshEntry:
        """保存层级 mesh（单个深度层）。"""
        return await self.save_mesh(
            project_id=project_id,
            mesh_data=mesh_data,
            scope="layer",
            target_id=layer_key,
            format=format,
            metadata={
                "object_count": object_count,
                "vertex_count": vertex_count,
                "face_count": face_count,
                "include_textures": include_textures,
                "error": error,
            },
        )

    async def save_scene_mesh(
        self,
        project_id: str,
        scene_id: str,
        mesh_data: bytes,
        format: str,
        object_count: int = 0,
        vertex_count: int = 0,
        face_count: int = 0,
        include_textures: bool = True,
        error: Optional[str] = None,
    ) -> MeshEntry:
        """保存场景 mesh（完整场景组合）。"""
        return await self.save_mesh(
            project_id=project_id,
            mesh_data=mesh_data,
            scope="scene",
            target_id=scene_id,
            format=format,
            metadata={
                "object_count": object_count,
                "vertex_count": vertex_count,
                "face_count": face_count,
                "include_textures": include_textures,
                "error": error,
            },
        )

    # ── 查询 ──────────────────────────────────────────────────────────────

    def list_mesh_exports(self, project_id: str) -> list[dict]:
        """列出项目中所有已导出的 mesh。"""
        manifest = self._read_manifest(project_id)
        return [
            {
                "mesh_id": m.mesh_id,
                "scope": m.scope,
                "target_id": m.target_id,
                "format": m.format,
                "file_name": m.file_name,
                "file_size": m.file_size,
                "file_sha256": m.file_sha256,
                "object_count": m.object_count,
                "vertex_count": m.vertex_count,
                "face_count": m.face_count,
                "include_textures": m.include_textures,
                "created_at": m.created_at,
                "download_url": f"/api/aicss/v2/meshes/{m.mesh_id}/download",
            }
            for m in manifest.meshes
        ]

    def get_mesh_export_info(self, project_id: str, mesh_id: str) -> Optional[dict]:
        """获取单个 mesh 导出的详细信息。"""
        manifest = self._read_manifest(project_id)
        for m in manifest.meshes:
            if m.mesh_id == mesh_id:
                return {
                    "mesh_id": m.mesh_id,
                    "scope": m.scope,
                    "target_id": m.target_id,
                    "format": m.format,
                    "file_name": m.file_name,
                    "file_size": m.file_size,
                    "file_sha256": m.file_sha256,
                    "object_count": m.object_count,
                    "vertex_count": m.vertex_count,
                    "face_count": m.face_count,
                    "include_textures": m.include_textures,
                    "created_at": m.created_at,
                    "error": m.error,
                    "download_url": f"/api/aicss/v2/meshes/{m.mesh_id}/download",
                }
        return None

    def get_mesh_file_path(self, project_id: str, mesh_id: str) -> Optional[Path]:
        """根据 mesh_id 解析文件路径。"""
        manifest = self._read_manifest(project_id)
        for m in manifest.meshes:
            if m.mesh_id == mesh_id:
                if m.scope == "object":
                    return self._mesh_objects_dir(project_id) / m.file_name
                elif m.scope == "layer":
                    return self._mesh_layers_dir(project_id) / m.file_name
                else:
                    return self._mesh_scenes_dir(project_id) / m.file_name
        return None

    def list_by_scope(self, project_id: str, scope: str) -> list[dict]:
        """按 scope 过滤列出 mesh。"""
        manifest = self._read_manifest(project_id)
        return [
            {
                "mesh_id": m.mesh_id,
                "target_id": m.target_id,
                "format": m.format,
                "file_name": m.file_name,
                "file_size": m.file_size,
                "created_at": m.created_at,
                "download_url": f"/api/aicss/v2/meshes/{m.mesh_id}/download",
            }
            for m in manifest.meshes
            if m.scope == scope
        ]

    # ── 删除 ──────────────────────────────────────────────────────────────

    async def delete_mesh_export(self, project_id: str, mesh_id: str) -> bool:
        """删除指定的 mesh 导出条目和文件。"""
        lock = await self._get_lock(project_id)
        async with lock:
            manifest = self._read_manifest(project_id)
            entry_to_delete = None
            for m in manifest.meshes:
                if m.mesh_id == mesh_id:
                    entry_to_delete = m
                    break

            if entry_to_delete is None:
                return False

            # 删除文件
            file_path = self.get_mesh_file_path(project_id, mesh_id)
            if file_path and file_path.exists():
                file_path.unlink()

            # 更新 manifest
            manifest.meshes = [m for m in manifest.meshes if m.mesh_id != mesh_id]
            self._write_manifest(project_id, manifest)
            return True

    # ── 清理 ──────────────────────────────────────────────────────────────

    async def clear_project_meshes(self, project_id: str) -> int:
        """删除项目中所有 mesh 导出文件。返回删除的文件数。"""
        lock = await self._get_lock(project_id)
        async with lock:
            manifest = self._read_manifest(project_id)
            count = 0

            for m in manifest.meshes:
                file_path = self.get_mesh_file_path(project_id, m.mesh_id)
                if file_path and file_path.exists():
                    file_path.unlink()
                    count += 1

            # 重写 manifest 为空
            self._write_manifest(project_id, MeshManifest(project_id=project_id))
            return count


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────


def _sanitize(name: str) -> str:
    """将任意字符串转换为安全的文件名。"""
    import re
    s = re.sub(r"[^A-Za-z0-9_\-]", "_", name or "")
    return s or "unnamed"


# ─────────────────────────────────────────────────────────────────────────────
# 单例导出
# ─────────────────────────────────────────────────────────────────────────────

project_store_mesh: ProjectStoreMesh = ProjectStoreMesh()
