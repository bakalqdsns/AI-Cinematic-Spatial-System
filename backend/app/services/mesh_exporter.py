"""
3D Mesh Exporter — Blender Headless Export Service

使用 Blender Headless Python API 将 Paper Diorama 场景数据导出为 GLB (glTF binary) 或 FBX 格式。

依赖:
    - Blender >= 3.0 已安装并加入系统 PATH
    - 或设置环境变量 BLENDER_EXECUTABLE 指定路径

导出粒度:
    - per-object: 每个检测到的物体单独导出为一个 mesh
    - per-layer: 每个深度层（前景/中景/背景/天空）导出为一个 mesh
    - full-scene: 所有层和物体组合导出为完整场景

支持的格式:
    - GLB (glTF Binary): 默认格式，跨平台兼容性最好
    - FBX: Autodesk FBX，用于 Unity/UE4/Maya

支持的材质通道:
    - Diffuse/BaseColor: paper_style 或 outlined 纹理
    - Normal: normal_map 纹理
"""

import base64
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("aicss")

# ─────────────────────────────────────────────────────────────────────────────
# Blender 可执行文件路径
# ─────────────────────────────────────────────────────────────────────────────

BLENDER_EXECUTABLE = os.environ.get("BLENDER_EXECUTABLE")


def _find_blender() -> Optional[str]:
    """查找系统中的 Blender 可执行文件。"""
    if BLENDER_EXECUTABLE and Path(BLENDER_EXECUTABLE).exists():
        return BLENDER_EXECUTABLE

    import sys
    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Blender Foundation/Blender 4.2/blender.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Blender Foundation/Blender 4.1/blender.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Blender Foundation/Blender 4.0/blender.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Blender Foundation/Blender 3.6/blender.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Blender Foundation/Blender/4.2/blender.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Blender Foundation/Blender/4.1/blender.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Blender Foundation/Blender/4.0/blender.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    else:
        for name in ["blender"]:
            result = shutil.which(name)
            if result:
                return result
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Vertex:
    x: float
    y: float
    z: float


@dataclass
class Face:
    indices: list[int]


@dataclass
class ObjectMeshData:
    object_id: str
    class_label: str
    parent_layer: str
    vertices: list[Vertex]
    faces: list[Face]
    normals: Optional[list[Vertex]] = None
    uvs: Optional[list[tuple[float, float]]] = None
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    diffuse_texture: Optional[str] = None
    normal_texture: Optional[str] = None
    thickness_texture: Optional[str] = None
    thickness: float = 0.05
    bevel_width: float = 0.005
    source_mask_url: Optional[str] = None


@dataclass
class LayerMeshData:
    layer_key: str
    layer_name: str
    width: float = 20.0
    height: float = 15.0
    thickness: float = 0.1
    position_z: float = 0.0
    diffuse_texture: Optional[str] = None
    normal_texture: Optional[str] = None
    thickness_texture: Optional[str] = None
    outlined_texture: Optional[str] = None
    offset_x: float = 0.0
    offset_y: float = 0.0
    bevel_width: float = 0.005


@dataclass
class SceneExportData:
    scene_id: str
    scene_width: float = 20.0
    scene_height: float = 15.0
    unit_scale: float = 1.0
    objects: list[ObjectMeshData] = field(default_factory=list)
    layers: list[LayerMeshData] = field(default_factory=list)
    textures_dir: Optional[str] = None
    output_format: str = "glb"
    include_textures: bool = True


@dataclass
class MeshExportResult:
    mesh_id: str
    file_path: str
    file_size: int
    file_sha256: str
    format: str
    object_count: int
    vertex_count: int
    face_count: int
    success: bool
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# 场景数据转换
# ─────────────────────────────────────────────────────────────────────────────


def build_object_mesh_from_detection(
    obj_id: str,
    class_label: str,
    bounding_box: dict,
    depth_meters: float,
    layer_key: str,
    texture_urls: Optional[dict] = None,
    thickness: float = 0.05,
    position_override: Optional[tuple[float, float, float]] = None,
) -> ObjectMeshData:
    """从检测结果构建 ObjectMeshData。"""
    scene_w, scene_h = 20.0, 15.0

    if position_override is not None:
        pos_x, pos_y, pos_z = position_override
    else:
        cx = bounding_box["x"] + bounding_box["w"] / 2
        cy = 1 - (bounding_box["y"] + bounding_box["h"] / 2)
        pos_x = (cx - 0.5) * scene_w
        pos_y = (cy - 0.5) * scene_h
        pos_z = (depth_meters / 50.0) * 10.0 - 5.0

    size_x = bounding_box["w"] * scene_w
    size_y = bounding_box["h"] * scene_h
    size_z = thickness

    hx, hy, hz = size_x / 2, size_y / 2, size_z / 2

    vertices = [
        Vertex(-hx, -hy, -hz), Vertex(hx, -hy, -hz), Vertex(hx, hy, -hz), Vertex(-hx, hy, -hz),
        Vertex(-hx, -hy, hz), Vertex(hx, -hy, hz), Vertex(hx, hy, hz), Vertex(-hx, hy, hz),
    ]

    faces = [
        Face([3, 2, 1, 0]), Face([4, 5, 6, 7]),
        Face([0, 1, 5, 4]), Face([2, 3, 7, 6]),
        Face([0, 4, 7, 3]), Face([1, 2, 6, 5]),
    ]

    return ObjectMeshData(
        object_id=obj_id,
        class_label=class_label,
        parent_layer=layer_key,
        vertices=vertices,
        faces=faces,
        position=(pos_x, pos_y, pos_z),
        scale=(1.0, 1.0, 1.0),
        diffuse_texture=texture_urls.get("diffuse") if texture_urls else None,
        normal_texture=texture_urls.get("normal") if texture_urls else None,
        thickness_texture=texture_urls.get("thickness") if texture_urls else None,
        thickness=thickness,
        bevel_width=0.005,
    )


def build_scene_from_frontend_data(
    analysis_result: dict,
    depth_split_result: dict,
    layer_assets: dict,
    object_assets: dict,
    billboard_offsets: dict,
    scene_id: str = "scene_001",
) -> SceneExportData:
    """从前端 3D 场景数据构建 SceneExportData。"""
    scene = SceneExportData(scene_id=scene_id)

    layer_z = {
        "sky": -20.0,
        "background": -12.0,
        "midground": -6.0,
        "foreground": -2.0,
    }

    for layer_key, z_pos in layer_z.items():
        asset = layer_assets.get(layer_key, {})
        if not asset:
            continue

        layer_data = LayerMeshData(
            layer_key=layer_key,
            layer_name=f"Depth Layer: {layer_key}",
            width=20.0,
            height=15.0,
            thickness=_layer_thickness(layer_key),
            position_z=z_pos,
            diffuse_texture=asset.get("rgbaUrl") or asset.get("paperStyleUrl"),
            normal_texture=asset.get("normalMapUrl"),
            outlined_texture=asset.get("outlinedUrl"),
        )
        scene.layers.append(layer_data)

    for obj in analysis_result.get("objects", []):
        obj_id = obj.get("id", "")
        layer_key = obj.get("layer", "foreground")
        depth = obj.get("depth", 0.0)
        bbox = obj.get("boundingBox", {})
        offset = billboard_offsets.get(obj_id, {})

        pos_x = offset.get("offsetX", 0.0)
        pos_y = 0.0
        pos_z = (depth / 50.0) * 10.0 - 5.0 + offset.get("offsetZ", 0.0)

        obj_asset = object_assets.get(obj_id, {})

        hx = bbox.get("w", 0.1) * 10.0
        hy = bbox.get("h", 0.1) * 7.5
        hz = 0.05

        vertices = [
            Vertex(-hx, -hy, -hz), Vertex(hx, -hy, -hz), Vertex(hx, hy, -hz), Vertex(-hx, hy, -hz),
            Vertex(-hx, -hy, hz), Vertex(hx, -hy, hz), Vertex(hx, hy, hz), Vertex(-hx, hy, hz),
        ]
        faces = [
            Face([3, 2, 1, 0]), Face([4, 5, 6, 7]),
            Face([0, 1, 5, 4]), Face([2, 3, 7, 6]),
            Face([0, 4, 7, 3]), Face([1, 2, 6, 5]),
        ]

        obj_data = ObjectMeshData(
            object_id=obj_id,
            class_label=obj.get("classLabel", "object"),
            parent_layer=layer_key,
            vertices=vertices,
            faces=faces,
            position=(pos_x, pos_y, pos_z),
            diffuse_texture=obj_asset.get("rgbaUrl") or obj_asset.get("paperStyleUrl"),
            normal_texture=obj_asset.get("normalMapUrl"),
            thickness=0.05,
        )
        scene.objects.append(obj_data)

    return scene


def _layer_thickness(layer_key: str) -> float:
    thickness_map = {
        "sky": 0.08,
        "background": 0.12,
        "midground": 0.20,
        "foreground": 0.30,
    }
    return thickness_map.get(layer_key, 0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Blender Python 脚本生成 — 使用 str.format() 避免 f-string 冲突
# ─────────────────────────────────────────────────────────────────────────────


def _generate_blender_script(scene: SceneExportData) -> str:
    """
    生成 Blender Python 脚本来构建场景并导出。

    使用 str.format() 而非 f-string，以避免 Blender 脚本内部的
    {expr} 被 Python 解释器误解析。
    """
    format_ext = "glb" if scene.output_format == "glb" else "fbx"
    scene_json = _serialize_scene_for_blender(scene)

    # raw string 模板：所有 { } 都是字面的，只有 {{ }} 在 .format() 后变为 { }
    # 最终替换的变量：unit_scale, scene_json, ext, fmt
    script_template = r'''
import bpy
import bmesh
import json
import os
import sys

# ── 清空默认场景 ─────────────────────────────────────────────────────────────
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

# 清理残留 data（mesh, material, image）
for block in list(bpy.data.meshes):
    if block.users == 0:
        bpy.data.meshes.remove(block)
for block in list(bpy.data.materials):
    if block.users == 0:
        bpy.data.materials.remove(block)
for block in list(bpy.data.images):
    if block.users == 0:
        bpy.data.images.remove(block)

# ── 场景设置 ─────────────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.render.engine = "CYCLES" if bpy.app.version >= (3, 6) else "BLENDER_EEVEE"
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0

UNIT_SCALE = {unit_scale}

# ── 加载场景数据 ──────────────────────────────────────────────────────────────
scene_data = {scene_json}


def make_box_mesh(name, w, h, d):
    """创建 BoxGeometry mesh。"""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    hw, hh, hd = w / 2, h / 2, d / 2
    verts = [
        bm.verts.new((-hw, -hh, -hd)),
        bm.verts.new(( hw, -hh, -hd)),
        bm.verts.new(( hw,  hh, -hd)),
        bm.verts.new((-hw,  hh, -hd)),
        bm.verts.new((-hw, -hh,  hd)),
        bm.verts.new(( hw, -hh,  hd)),
        bm.verts.new(( hw,  hh,  hd)),
        bm.verts.new((-hw,  hh,  hd)),
    ]
    face_verts = [
        [3, 2, 1, 0], [4, 5, 6, 7],
        [0, 1, 5, 4], [2, 3, 7, 6],
        [0, 4, 7, 3], [1, 2, 6, 5],
    ]
    for fv in face_verts:
        try:
            vs = [verts[i] for i in fv]
            bm.faces.new(vs)
        except Exception:
            pass
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def make_paper_material(name, diffuse_path, normal_path, bevel_w):
    """创建纸模材质（Principled BSDF + Image Texture）。"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (0, 0)
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    if diffuse_path:
        try:
            img = bpy.data.images.load(diffuse_path)
            img.colorspace_settings.name = "sRGB"
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.location = (-400, 100)
            links.new(tex.outputs["Color"], principled.inputs["Base Color"])
        except Exception as exc:
            print("[WARN] Could not load diffuse", diffuse_path, ":", exc)

    if normal_path:
        try:
            nimg = bpy.data.images.load(normal_path)
            nimg.colorspace_settings.name = "Non-Color"
            ntex = nodes.new("ShaderNodeTexImage")
            ntex.image = nimg
            ntex.location = (-400, -150)
            normal_node = nodes.new("ShaderNodeNormalMap")
            normal_node.location = (-100, -150)
            links.new(ntex.outputs["Color"], normal_node.inputs["Color"])
            links.new(normal_node.outputs["Normal"], principled.inputs["Normal"])
        except Exception as exc:
            print("[WARN] Could not load normal", normal_path, ":", exc)

    principled.inputs["Roughness"].default_value = 0.9
    principled.inputs["Specular IOR Level"].default_value = 0.0
    return mat


# ── 构建层 Meshes ─────────────────────────────────────────────────────────────
for layer in scene_data.get("layers", []):
    w = layer.get("width", 20.0)
    h = layer.get("height", 15.0)
    d = layer.get("thickness", 0.1)
    z_pos = layer.get("position_z", 0.0)
    bevel_w = layer.get("bevel_width", 0.005)
    diff_path = layer.get("diffuse_texture", "") or ""
    norm_path = layer.get("normal_texture", "") or ""

    if diff_path and diff_path.startswith("data:"):
        diff_path = ""
    if norm_path and norm_path.startswith("data:"):
        norm_path = ""

    layer_key = str(layer.get("layer_key", "layer"))
    mesh = make_box_mesh("Layer_" + layer_key, w, h, d)
    obj = bpy.data.objects.new("Layer_" + layer_key, mesh)
    obj.location = (0, 0, z_pos)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    if diff_path or norm_path:
        mat = make_paper_material("Mat_Layer_" + layer_key, diff_path, norm_path, bevel_w)
        mesh.materials.append(mat)

    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = bevel_w
    bevel.segments = 2
    bevel.limit_method = "ANGLE"


# ── 构建物体 Meshes ────────────────────────────────────────────────────────────
for obj_data in scene_data.get("objects", []):
    verts_data = obj_data.get("vertices", [])
    faces_data = obj_data.get("faces", [])
    pos = tuple(obj_data.get("position", [0, 0, 0]))
    scale = tuple(obj_data.get("scale", [1, 1, 1]))
    bevel_w = obj_data.get("bevel_width", 0.005)
    diff_path = obj_data.get("diffuse_texture", "") or ""
    norm_path = obj_data.get("normal_texture", "") or ""

    if diff_path and diff_path.startswith("data:"):
        diff_path = ""
    if norm_path and norm_path.startswith("data:"):
        norm_path = ""

    obj_id = str(obj_data.get("object_id", "object"))

    mesh = bpy.data.meshes.new("Mesh_" + obj_id)
    bm = bmesh.new()

    vert_map = {{}}
    for vi, v in enumerate(verts_data):
        vx = float(v.get("x", 0)) * scale[0]
        vy = float(v.get("y", 0)) * scale[1]
        vz = float(v.get("z", 0)) * scale[2]
        vert_map[vi] = bm.verts.new((vx, vy, vz))
    bm.verts.ensure_lookup_table()

    for f in faces_data:
        fv_indices = f.get("indices", [])
        if len(fv_indices) >= 3:
            try:
                vs = [vert_map[i] for i in fv_indices if i in vert_map]
                if len(vs) >= 3:
                    bm.faces.new(vs)
            except Exception:
                pass

    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("Object_" + obj_id, mesh)
    obj.location = pos
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj

    if diff_path or norm_path:
        mat = make_paper_material("Mat_Object_" + obj_id, diff_path, norm_path, bevel_w)
        mesh.materials.append(mat)

    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = bevel_w
    bevel.segments = 2


# ── 导出 ──────────────────────────────────────────────────────────────────────
import sys as _sys
import os as _os
output_path = _sys.argv[-1] if len(_sys.argv) > 1 else _os.path.join(_os.path.expanduser("~"), "aicss_export.{ext}")
output_format = "{fmt}"

if output_format == "glb":
    bpy.ops.export_scene.gltf(
        filepath=output_path,
        use_selection=False,
        export_format="GLB",
        export_materials="EXPORT",
        export_colors=True,
        export_normals=True,
        export_texcoords=True,
        export_apply=True,
        export_lights=False,
        export_cameras=False,
        export_yup=True,
        export_animations=False,
    )
else:
    bpy.ops.export_scene.fbx(
        filepath=output_path,
        use_selection=False,
        global_scale=1.0,
        axis_forward="-Z",
        axis_up="Y",
        object_types={{"MESH"}},
        use_mesh_modifiers=True,
        mesh_smooth_type="FACE",
        bake_space_transform=True,
    )

print("[OK] Exported to", output_path)
'''  # END raw template

    # 在 .format() 中：
    # {{ }} → { }  （字面的花括号）
    # {{{vi}}} → {vi} → vert_map[vi]
    # {{{{"MESH"}}}} → {"MESH"} → object_types={"MESH"}
    return script_template.format(
        unit_scale=scene.unit_scale,
        scene_json=scene_json,
        ext=format_ext,
        fmt=scene.output_format,
    )


def _serialize_scene_for_blender(scene: SceneExportData) -> str:
    """将 SceneExportData 序列化为 JSON 供 Blender 脚本内联读取。"""
    data = {
        "scene_id": scene.scene_id,
        "scene_width": scene.scene_width,
        "scene_height": scene.scene_height,
        "layers": [],
        "objects": [],
    }

    for layer in scene.layers:
        data["layers"].append({
            "layer_key": layer.layer_key,
            "layer_name": layer.layer_name,
            "width": layer.width,
            "height": layer.height,
            "thickness": layer.thickness,
            "position_z": layer.position_z,
            "diffuse_texture": layer.diffuse_texture or "",
            "normal_texture": layer.normal_texture or "",
            "outlined_texture": layer.outlined_texture or "",
            "bevel_width": layer.bevel_width,
        })

    for obj in scene.objects:
        data["objects"].append({
            "object_id": obj.object_id,
            "class_label": obj.class_label,
            "parent_layer": obj.parent_layer,
            "vertices": [{"x": v.x, "y": v.y, "z": v.z} for v in obj.vertices],
            "faces": [{"indices": f.indices} for f in obj.faces],
            "position": obj.position,
            "rotation": obj.rotation,
            "scale": obj.scale,
            "diffuse_texture": obj.diffuse_texture or "",
            "normal_texture": obj.normal_texture or "",
            "thickness_texture": obj.thickness_texture or "",
            "thickness": obj.thickness,
            "bevel_width": obj.bevel_width,
        })

    return json.dumps(data, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# 纹理文件下载（处理 data URL）
# ─────────────────────────────────────────────────────────────────────────────


def _download_base64_image(data_url: str, cache_dir: Path) -> Optional[str]:
    """将 base64 data URL 保存为临时文件并返回路径。"""
    if not data_url or not data_url.startswith("data:"):
        return data_url if data_url else None

    try:
        header, b64_data = data_url.split(",", 1)
        mime_type = header.split(";")[0].replace("data:", "")
        ext = "png" if "png" in mime_type else "jpg"
        content = base64.b64decode(b64_data)

        file_name = f"{uuid.uuid4().hex[:12]}.{ext}"
        file_path = cache_dir / file_name
        file_path.write_bytes(content)
        return str(file_path)
    except Exception as e:
        logger.warning(f"[mesh_exporter] Failed to decode base64 image: {e}")
        return None


def _prepare_textures(scene: SceneExportData, cache_dir: Path) -> Path:
    """下载所有 base64 纹理到临时目录，返回纹理目录路径。"""
    texture_dir = cache_dir / "textures"
    texture_dir.mkdir(exist_ok=True)

    for layer in scene.layers:
        for attr_name in ["diffuse_texture", "normal_texture", "thickness_texture", "outlined_texture"]:
            url = getattr(layer, attr_name, None)
            if url and url.startswith("data:"):
                saved = _download_base64_image(url, texture_dir)
                if saved:
                    setattr(layer, attr_name, saved)

    for obj in scene.objects:
        for attr_name in ["diffuse_texture", "normal_texture", "thickness_texture"]:
            url = getattr(obj, attr_name, None)
            if url and url.startswith("data:"):
                saved = _download_base64_image(url, texture_dir)
                if saved:
                    setattr(obj, attr_name, saved)

    return texture_dir


# ─────────────────────────────────────────────────────────────────────────────
# 核心导出函数
# ─────────────────────────────────────────────────────────────────────────────


def export_scene(
    scene: SceneExportData,
    output_dir: Optional[str] = None,
    output_format: Optional[str] = None,
) -> MeshExportResult:
    """使用 Blender Headless 将场景导出为 GLB/FBX 格式。"""
    blender_path = _find_blender()
    if not blender_path:
        return MeshExportResult(
            mesh_id=scene.scene_id,
            file_path="",
            file_size=0,
            file_sha256="",
            format=scene.output_format,
            object_count=len(scene.objects),
            vertex_count=sum(len(o.vertices) for o in scene.objects),
            face_count=sum(len(o.faces) for o in scene.objects),
            success=False,
            error="Blender executable not found. Install Blender and add it to PATH, "
                   "or set BLENDER_EXECUTABLE environment variable.",
        )

    fmt = output_format or scene.output_format
    ext = "glb" if fmt == "glb" else "fbx"

    with tempfile.TemporaryDirectory(prefix="aicss_mesh_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        if scene.include_textures:
            texture_dir = _prepare_textures(scene, tmp_path)
            scene.textures_dir = str(texture_dir)

        blender_script = _generate_blender_script(scene)
        script_path = tmp_path / "export_scene.py"
        script_path.write_text(blender_script, encoding="utf-8")

        out_dir = Path(output_dir) if output_dir else tmp_path
        out_dir.mkdir(parents=True, exist_ok=True)
        output_file = out_dir / f"{scene.scene_id}.{ext}"

        try:
            result = subprocess.run(
                [blender_path, "--background", "--python", str(script_path), "--", str(output_file)],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                return MeshExportResult(
                    mesh_id=scene.scene_id,
                    file_path=str(output_file),
                    file_size=0,
                    file_sha256="",
                    format=fmt,
                    object_count=len(scene.objects),
                    vertex_count=sum(len(o.vertices) for o in scene.objects),
                    face_count=sum(len(o.faces) for o in scene.objects),
                    success=False,
                    error=f"Blender export failed (exit {result.returncode}): {result.stderr[:500]}",
                )

            if not output_file.exists() or output_file.stat().st_size == 0:
                return MeshExportResult(
                    mesh_id=scene.scene_id,
                    file_path=str(output_file),
                    file_size=0,
                    file_sha256="",
                    format=fmt,
                    object_count=len(scene.objects),
                    vertex_count=sum(len(o.vertices) for o in scene.objects),
                    face_count=sum(len(o.faces) for o in scene.objects),
                    success=False,
                    error="Blender completed but output file not found or empty",
                )

            file_bytes = output_file.read_bytes()
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()

            logger.info(
                f"[mesh_exporter] Exported {output_file} "
                f"({output_file.stat().st_size:,} bytes, {len(scene.objects)} objects)"
            )

            return MeshExportResult(
                mesh_id=scene.scene_id,
                file_path=str(output_file),
                file_size=output_file.stat().st_size,
                file_sha256=sha256_hash,
                format=fmt,
                object_count=len(scene.objects),
                vertex_count=sum(len(o.vertices) for o in scene.objects),
                face_count=sum(len(o.faces) for o in scene.objects),
                success=True,
            )

        except subprocess.TimeoutExpired:
            return MeshExportResult(
                mesh_id=scene.scene_id,
                file_path=str(output_file),
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=len(scene.objects),
                vertex_count=sum(len(o.vertices) for o in scene.objects),
                face_count=sum(len(o.faces) for o in scene.objects),
                success=False,
                error="Blender export timed out after 300 seconds",
            )
        except FileNotFoundError:
            return MeshExportResult(
                mesh_id=scene.scene_id,
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=len(scene.objects),
                vertex_count=sum(len(o.vertices) for o in scene.objects),
                face_count=sum(len(o.faces) for o in scene.objects),
                success=False,
                error=f"Blender executable not found at: {blender_path}",
            )
        except Exception as e:
            return MeshExportResult(
                mesh_id=scene.scene_id,
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=len(scene.objects),
                vertex_count=sum(len(o.vertices) for o in scene.objects),
                face_count=sum(len(o.faces) for o in scene.objects),
                success=False,
                error=f"Unexpected error: {type(e).__name__}: {e}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────────────────────────────────────


def export_objects_only(
    objects: list[dict],
    layer_assets: dict,
    object_assets: dict,
    billboard_offsets: Optional[dict] = None,
    scene_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "glb",
    include_textures: bool = True,
) -> MeshExportResult:
    """仅导出检测到的物体（不含深度层）。"""
    scene = SceneExportData(
        scene_id=scene_id or f"objects_{uuid.uuid4().hex[:8]}",
        output_format=output_format,
        include_textures=include_textures,
    )

    layer_z = {"sky": -20.0, "background": -12.0, "midground": -6.0, "foreground": -2.0}
    offsets = billboard_offsets or {}

    for obj in objects:
        obj_id = obj.get("id", "")
        layer_key = obj.get("layer", "foreground")
        depth = obj.get("depth", 0.0)
        bbox = obj.get("boundingBox", {})
        asset = object_assets.get(obj_id, {})
        offset = offsets.get(obj_id, {})

        pos_x = offset.get("offsetX", 0.0)
        pos_z = (depth / 50.0) * 10.0 - 5.0 + offset.get("offsetZ", 0.0)

        texture_urls = {
            "diffuse": asset.get("rgbaUrl") or asset.get("paperStyleUrl"),
            "normal": asset.get("normalMapUrl"),
            "thickness": asset.get("thicknessGrayUrl"),
        }

        obj_data = build_object_mesh_from_detection(
            obj_id=obj_id,
            class_label=obj.get("classLabel", "object"),
            bounding_box=bbox,
            depth_meters=depth,
            layer_key=layer_key,
            texture_urls=texture_urls,
            position_override=(pos_x, 0.0, pos_z),
        )
        scene.objects.append(obj_data)

    return export_scene(scene, output_dir, output_format)


def export_layers_only(
    layer_assets: dict,
    scene_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "glb",
    include_textures: bool = True,
) -> MeshExportResult:
    """仅导出深度层（不含单个物体）。"""
    layer_z = {"sky": -20.0, "background": -12.0, "midground": -6.0, "foreground": -2.0}

    scene = SceneExportData(
        scene_id=scene_id or f"layers_{uuid.uuid4().hex[:8]}",
        output_format=output_format,
        include_textures=include_textures,
    )

    for layer_key, z_pos in layer_z.items():
        asset = layer_assets.get(layer_key, {})
        if not asset:
            continue

        layer_data = LayerMeshData(
            layer_key=layer_key,
            layer_name=f"Depth Layer: {layer_key}",
            width=20.0,
            height=15.0,
            thickness=_layer_thickness(layer_key),
            position_z=z_pos,
            diffuse_texture=asset.get("rgbaUrl") or asset.get("paperStyleUrl"),
            normal_texture=asset.get("normalMapUrl"),
            outlined_texture=asset.get("outlinedUrl"),
        )
        scene.layers.append(layer_data)

    return export_scene(scene, output_dir, output_format)


def export_full_scene(
    analysis_result: dict,
    depth_split_result: dict,
    layer_assets: dict,
    object_assets: dict,
    billboard_offsets: dict,
    scene_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "glb",
    include_textures: bool = True,
) -> MeshExportResult:
    """导出完整场景（层 + 物体）。"""
    scene = build_scene_from_frontend_data(
        analysis_result=analysis_result,
        depth_split_result=depth_split_result,
        layer_assets=layer_assets,
        object_assets=object_assets,
        billboard_offsets=billboard_offsets,
        scene_id=scene_id or f"scene_{uuid.uuid4().hex[:8]}",
    )
    scene.output_format = output_format
    scene.include_textures = include_textures
    return export_scene(scene, output_dir, output_format)


# ─────────────────────────────────────────────────────────────────────────────
# Blender 可用性检查
# ─────────────────────────────────────────────────────────────────────────────

def check_blender_available() -> dict:
    """检查 Blender 是否可用，返回诊断信息。"""
    blender_path = _find_blender()

    if blender_path:
        try:
            result = subprocess.run(
                [blender_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = result.stdout.strip().split("\n")[0] if result.stdout else "unknown"
            return {
                "available": True,
                "path": blender_path,
                "version": version,
                "message": "Blender is available for 3D mesh export",
            }
        except Exception as e:
            return {
                "available": False,
                "path": blender_path,
                "version": "unknown",
                "error": str(e),
                "message": "Blender found but failed to run",
            }

    return {
        "available": False,
        "path": None,
        "version": None,
        "error": None,
        "message": (
            "Blender not found. Install Blender >= 3.0 and add it to system PATH, "
            "or set BLENDER_EXECUTABLE environment variable."
        ),
        "install_hint": {
            "windows": "Download from https://www.blender.org/download/",
            "linux": "sudo apt install blender",
            "macos": "brew install blender",
        },
    }
