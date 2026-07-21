"""
3D Mesh Export API Endpoints
REST endpoints for exporting Paper Diorama scenes as GLB (glTF binary) or FBX meshes.

Provides:
  POST /api/aicss/v2/meshes/export-objects   — Export detected objects as 3D meshes
  POST /api/aicss/v2/meshes/export-layers    — Export depth layers as 3D meshes
  POST /api/aicss/v2/meshes/export-scene    — Export full scene (layers + objects)
  GET  /api/aicss/v2/meshes/list            — List all mesh exports for a project
  GET  /api/aicss/v2/meshes/{mesh_id}/info — Get mesh export metadata
  GET  /api/aicss/v2/meshes/{mesh_id}/download — Download mesh file
  DELETE /api/aicss/v2/meshes/{mesh_id}      — Delete a mesh export
  GET  /api/aicss/v2/meshes/check          — Check Blender availability

Reference: docs/FBX_EXPORT_IMPLEMENTATION.md
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.mesh_exporter import (
    export_objects_only,
    export_layers_only,
    export_full_scene,
    check_blender_available,
    MeshExportResult,
)
from app.services.project_store_mesh import project_store_mesh

logger = logging.getLogger("aicss")

router = APIRouter(prefix="/v2/meshes", tags=["v2 - 3D Mesh Export"])


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────


class ExportObjectsRequest(BaseModel):
    """导出检测到的物体。"""
    project_id: Optional[str] = Field(None, description="项目 ID（可选，不提供则不持久化）")
    analysis_result: dict = Field(..., description="AicssResult JSON（objects 字段必须）")
    object_ids: Optional[list[str]] = Field(
        None,
        description="要导出的物体 ID 列表（None = 全部）"
    )
    object_assets: dict = Field(
        default_factory=dict,
        description="objectDioramaAssets 字典 { objectId: asset }"
    )
    billboard_offsets: dict = Field(
        default_factory=dict,
        description="billboardOffsets 字典 { objectId: { offsetX, offsetZ } }"
    )
    format: str = Field("glb", description="导出格式: glb | fbx")
    include_textures: bool = Field(True, description="是否嵌入纹理")


class ExportLayersRequest(BaseModel):
    """导出深度分层。"""
    project_id: Optional[str] = Field(None)
    layer_assets: dict = Field(..., description="depthLayerDioramaAssets 字典")
    format: str = Field("glb", description="glb | fbx")
    include_textures: bool = Field(True)


class ExportSceneRequest(BaseModel):
    """导出完整场景。"""
    project_id: Optional[str] = Field(None, description="项目 ID（可选，不提供则不持久化）")
    analysis_result: dict = Field(..., description="完整 AicssResult")
    depth_split_result: dict = Field(default_factory=dict, description="前端 splitDepthLayers() 结果")
    layer_assets: dict = Field(..., description="depthLayerDioramaAssets 字典")
    object_assets: dict = Field(default_factory=dict, description="objectDioramaAssets 字典")
    billboard_offsets: dict = Field(default_factory=dict, description="物体 3D 偏移")
    format: str = Field("glb", description="glb | fbx")
    include_textures: bool = Field(True)


class MeshExportResponse(BaseModel):
    """导出结果响应。"""
    mesh_id: str
    scope: str                        # "object" | "layer" | "scene"
    format: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    file_sha256: Optional[str] = None
    object_count: int
    vertex_count: int
    face_count: int
    include_textures: bool
    success: bool
    error: Optional[str] = None
    blender_available: bool
    project_id: Optional[str] = None
    download_url: Optional[str] = None


class MeshListResponse(BaseModel):
    meshes: list[dict]


class BlenderCheckResponse(BaseModel):
    available: bool
    path: Optional[str] = None
    version: Optional[str] = None
    message: str
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_response(
    result: MeshExportResult,
    scope: str,
    project_id: Optional[str],
    blender_available: bool,
) -> MeshExportResponse:
    """将 MeshExportResult 转换为 API 响应。"""
    return MeshExportResponse(
        mesh_id=result.mesh_id,
        scope=scope,
        format=result.format,
        file_name=Path(result.file_path).name if result.file_path else None,
        file_size=result.file_size or None,
        file_sha256=result.file_sha256 or None,
        object_count=result.object_count,
        vertex_count=result.vertex_count,
        face_count=result.face_count,
        include_textures=True,
        success=result.success,
        error=result.error,
        blender_available=blender_available,
        project_id=project_id,
        download_url=(
            f"/api/aicss/v2/meshes/{result.mesh_id}/download"
            if result.success and project_id else None
        ),
    )


def _format_to_ext(fmt: str) -> str:
    """验证并规范化格式字符串。"""
    fmt = fmt.lower().strip()
    if fmt not in ("glb", "fbx"):
        raise HTTPException(status_code=400, detail="format must be 'glb' or 'fbx'")
    return fmt


# ─────────────────────────────────────────────────────────────────────────────
# POST /export-objects
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/export-objects", response_model=MeshExportResponse)
async def api_export_objects(request: ExportObjectsRequest):
    """
    将检测到的物体导出为 3D mesh 文件。

    支持按 object_ids 过滤，也支持传入 object_assets 以包含纹理。
    Blender Headless 在后台完成 mesh 构建和导出。
    """
    fmt = _format_to_ext(request.format)

    # Blender 可用性检查
    blender_info = check_blender_available()
    if not blender_info["available"]:
        return _to_response(
            MeshExportResult(
                mesh_id="",
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=0,
                vertex_count=0,
                face_count=0,
                success=False,
                error=blender_info["message"],
            ),
            scope="object",
            project_id=request.project_id,
            blender_available=False,
        )

    # 过滤物体
    objects = request.analysis_result.get("objects", [])
    if request.object_ids:
        objects = [o for o in objects if o.get("id") in request.object_ids]

    if not objects:
        raise HTTPException(status_code=400, detail="No objects to export")

    # 导出
    result = export_objects_only(
        objects=objects,
        layer_assets={},
        object_assets=request.object_assets,
        billboard_offsets=request.billboard_offsets,
        scene_id=f"objects_{Path(request.project_id or 'temp').name}" if request.project_id else None,
        output_format=fmt,
        include_textures=request.include_textures,
    )

    # 持久化
    if request.project_id and result.success and result.file_path:
        try:
            mesh_bytes = Path(result.file_path).read_bytes()
            entry = await project_store_mesh.save_object_mesh(
                project_id=request.project_id,
                object_id=",".join(o.get("id", "") for o in objects[:3]) or "objects",
                mesh_data=mesh_bytes,
                format=fmt,
                object_count=result.object_count,
                vertex_count=result.vertex_count,
                face_count=result.face_count,
                include_textures=request.include_textures,
            )
            result.mesh_id = entry.mesh_id
        except Exception as e:
            logger.warning(f"[mesh] Failed to persist object mesh: {e}")

    return _to_response(result, scope="object", project_id=request.project_id, blender_available=True)


# ─────────────────────────────────────────────────────────────────────────────
# POST /export-layers
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/export-layers", response_model=MeshExportResponse)
async def api_export_layers(request: ExportLayersRequest):
    """
    将深度分层导出为 3D mesh 文件。

    每个有纹理的层（foreground/midground/background/sky）单独导出为一个 mesh，
    包含 BoxGeometry 和 paper diorama 纹理。
    """
    fmt = _format_to_ext(request.format)

    blender_info = check_blender_available()
    if not blender_info["available"]:
        return _to_response(
            MeshExportResult(
                mesh_id="",
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=0,
                vertex_count=0,
                face_count=0,
                success=False,
                error=blender_info["message"],
            ),
            scope="layer",
            project_id=request.project_id,
            blender_available=False,
        )

    if not request.layer_assets:
        raise HTTPException(status_code=400, detail="No layer assets provided")

    result = export_layers_only(
        layer_assets=request.layer_assets,
        scene_id=f"layers_{Path(request.project_id or 'temp').name}" if request.project_id else None,
        output_format=fmt,
        include_textures=request.include_textures,
    )

    if request.project_id and result.success and result.file_path:
        try:
            mesh_bytes = Path(result.file_path).read_bytes()
            layer_keys = list(request.layer_assets.keys())
            entry = await project_store_mesh.save_layer_mesh(
                project_id=request.project_id,
                layer_key="+".join(layer_keys) if layer_keys else "layers",
                mesh_data=mesh_bytes,
                format=fmt,
                object_count=result.object_count,
                vertex_count=result.vertex_count,
                face_count=result.face_count,
                include_textures=request.include_textures,
            )
            result.mesh_id = entry.mesh_id
        except Exception as e:
            logger.warning(f"[mesh] Failed to persist layer mesh: {e}")

    return _to_response(result, scope="layer", project_id=request.project_id, blender_available=True)


# ─────────────────────────────────────────────────────────────────────────────
# POST /export-scene
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/export-scene", response_model=MeshExportResponse)
async def api_export_scene(request: ExportSceneRequest):
    """
    导出完整场景（所有深度层 + 所有物体）。

    生成一个包含所有 paper diorama 元素的组合 GLB/FBX 文件。
    """
    fmt = _format_to_ext(request.format)

    blender_info = check_blender_available()
    if not blender_info["available"]:
        return _to_response(
            MeshExportResult(
                mesh_id="",
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=0,
                vertex_count=0,
                face_count=0,
                success=False,
                error=blender_info["message"],
            ),
            scope="scene",
            project_id=request.project_id,
            blender_available=False,
        )

    objects = request.analysis_result.get("objects", [])
    if not objects and not request.layer_assets:
        raise HTTPException(
            status_code=400,
            detail="No objects or layers to export. Provide analysis_result or layer_assets."
        )

    result = export_full_scene(
        analysis_result=request.analysis_result,
        depth_split_result=request.depth_split_result,
        layer_assets=request.layer_assets,
        object_assets=request.object_assets,
        billboard_offsets=request.billboard_offsets,
        scene_id=(
            f"scene_{Path(request.project_id).name}"
            if request.project_id else None
        ),
        output_format=fmt,
        include_textures=request.include_textures,
    )

    if request.project_id and result.success and result.file_path:
        try:
            mesh_bytes = Path(result.file_path).read_bytes()
            scene_id = result.scene_id
            entry = await project_store_mesh.save_scene_mesh(
                project_id=request.project_id,
                scene_id=scene_id or "full_scene",
                mesh_data=mesh_bytes,
                format=fmt,
                object_count=result.object_count,
                vertex_count=result.vertex_count,
                face_count=result.face_count,
                include_textures=request.include_textures,
            )
            result.mesh_id = entry.mesh_id
        except Exception as e:
            logger.warning(f"[mesh] Failed to persist scene mesh: {e}")

    return _to_response(result, scope="scene", project_id=request.project_id, blender_available=True)


# ─────────────────────────────────────────────────────────────────────────────
# GET /list
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/list", response_model=MeshListResponse)
async def api_list_meshes(project_id: str):
    """
    列出项目中所有已导出的 mesh 文件。

    支持 ?scope=object|layer|scene 过滤。
    """
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    scope = None
    # Note: FastAPI 会将 scope=object 作为 query param
    meshes = project_store_mesh.list_mesh_exports(project_id)
    return MeshListResponse(meshes=meshes)


# ─────────────────────────────────────────────────────────────────────────────
# GET /{mesh_id}/info
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{mesh_id}/info")
async def api_mesh_info(mesh_id: str, project_id: str):
    """获取单个 mesh 导出的元数据。"""
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    info = project_store_mesh.get_mesh_export_info(project_id, mesh_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Mesh {mesh_id} not found")
    return info


# ─────────────────────────────────────────────────────────────────────────────
# GET /{mesh_id}/download
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{mesh_id}/download")
async def api_download_mesh(mesh_id: str, project_id: str):
    """
    下载指定的 mesh 文件。

    支持 GLB 和 FBX 格式。
    """
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    file_path = project_store_mesh.get_mesh_file_path(project_id, mesh_id)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Mesh file {mesh_id} not found or not persisted")

    info = project_store_mesh.get_mesh_export_info(project_id, mesh_id)
    format_str = info.get("format", "glb") if info else "glb"

    ext = format_str.lower()
    media_type = (
        "model/gltf-binary"
        if ext == "glb"
        else "application/octet-stream"
    )

    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /{mesh_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{mesh_id}")
async def api_delete_mesh(mesh_id: str, project_id: str):
    """删除指定的 mesh 导出条目和文件。"""
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    deleted = await project_store_mesh.delete_mesh_export(project_id, mesh_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Mesh {mesh_id} not found")
    return {"deleted": True, "mesh_id": mesh_id}


# ─────────────────────────────────────────────────────────────────────────────
# GET /check — Blender 可用性检查
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/check", response_model=BlenderCheckResponse)
async def api_check_blender():
    """
    检查 Blender 是否可用于 3D mesh 导出。

    返回 Blender 路径、版本号和可用性状态。
    """
    info = check_blender_available()
    return BlenderCheckResponse(**info)
