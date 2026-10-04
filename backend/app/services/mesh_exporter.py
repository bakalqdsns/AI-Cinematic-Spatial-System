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
    depth_value: Optional[float] = None  # 精细 Z 偏移：0-255 深度值
    use_displacement: bool = False  # 是否使用 displacement mesh（非均匀厚度）


@dataclass
class StripBillboardData:
    """
    Strip-stack 逐层剥离流水线的单条 billboard mesh 数据。

    每条 StripStep（前端 push 到 store 的 stripStack 数组里的一项）对应一个
    独立的 PlaneGeometry billboard,贴在用户剥离该层时该 region 的原始深度位置。

    厚度按 _billboard_thickness() 固定值（按 depthLayer 选择），不依赖 paper-diorama
    厚度纹理（避免对 LaMa-inpainted region 强行套 distanceTransform 造成过度厚度）。
    """
    region_id: str
    depth_layer_key: str  # "foreground" | "midground" | "background" | "sky"
    depth_value: int  # 0-255, 与前端 depthUtils.zForRegion() 对齐
    color_index: int  # 第几条 strip (0-based, 用于防 z-fighting 微调)
    layer_z: float  # 已在 Python 端算好的 Z = base_z(depth_layer) + fine_offset(depth_value)
    width: float = 20.0
    height: float = 15.0
    thickness: float = 0.20
    diffuse_texture: Optional[str] = None  # billboardUrl RGBA (data: URL or path)
    layer_polygon: Optional[list[list[float]]] = None  # 归一化 0-1 UV 多边形
    bevel_width: float = 0.005


@dataclass
class BackgroundPlaneData:
    """
    strip-stack 流水线最终 inpaint 背景的 BackgroundPlane。

    这是最后一条 StripStep.inpaintResultUrl 解码出来的大背景贴图,
    作为最远景（z=-25）渲染为一整张平面 mesh。
    """
    texture: str  # data: URL or path
    width: float = 30.0
    height: float = 20.0
    z: float = -25.0
    bevel_width: float = 0.005


@dataclass
class SceneExportData:
    scene_id: str
    scene_width: float = 20.0
    scene_height: float = 15.0
    unit_scale: float = 1.0
    objects: list[ObjectMeshData] = field(default_factory=list)
    layers: list[LayerMeshData] = field(default_factory=list)
    strip_billboards: list[StripBillboardData] = field(default_factory=list)
    background_plane: Optional[BackgroundPlaneData] = None
    textures_dir: Optional[str] = None
    output_format: str = "glb"
    include_textures: bool = True
    # T14 — 灯光：dict 格式 {key, fill, rim}，每段 {type, energy, color, location, rotation}
    lighting: dict = field(default_factory=dict)
    # T14 — 是否导出灯到 GLB（默认 True；其他 viewer 才能看到灯）
    include_lights: bool = True


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
    scene_id: Optional[str] = None
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

        # 从 asset 中获取 depth_value（精细 Z 偏移）
        depth_value = asset.get("depthValue")
        use_displacement = bool(asset.get("thicknessGrayUrl"))

        # 应用精细 Z 偏移
        fine_z = _compute_fine_z_offset(depth_value, z_pos)

        layer_data = LayerMeshData(
            layer_key=layer_key,
            layer_name=f"Depth Layer: {layer_key}",
            width=20.0,
            height=15.0,
            thickness=_layer_thickness(layer_key),
            position_z=fine_z,
            diffuse_texture=asset.get("rgbaUrl") or asset.get("paperStyleUrl"),
            normal_texture=asset.get("normalMapUrl"),
            thickness_texture=asset.get("thicknessGrayUrl"),
            outlined_texture=asset.get("outlinedUrl"),
            depth_value=depth_value,
            use_displacement=use_displacement,
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


# Strip-stack billboard 厚度常量（与 _layer_thickness 共享同一张表，但语义独立：
# billboard 是单条 LaMa 剥离产物，固定厚度足以表现 z-order 差异）
_STRIP_BILLBOARD_THICKNESS = {
    "foreground": 0.30,
    "midground": 0.20,
    "background": 0.12,
    "sky": 0.08,
}


def _billboard_thickness(depth_layer_key: str) -> float:
    """strip-stack 单条 billboard 的固定厚度（按 depthLayer 选择）。"""
    return _STRIP_BILLBOARD_THICKNESS.get(depth_layer_key, 0.20)


def _compute_fine_z_offset(depth_value: Optional[float], base_z: float) -> float:
    """
    基于 depth_value (0-255) 计算精细 Z 偏移。

    depthValue 128 = 中性（无偏移），偏离 128 越多偏移越大。
    映射范围：depthValue 0 → +0.64 单位，depthValue 255 → -0.64 单位
    （与前端 depthUtils.ts 的 zForRegion() 逻辑一致）
    """
    if depth_value is None:
        return base_z
    normalized = (depth_value - 128.0) / 128.0  # -1 to +1
    fine_offset = normalized * 0.64  # ±0.64 world units
    return base_z + fine_offset


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
# scene_data.json 路径通过环境变量 AICSS_SCENE_DATA_PATH 传入（由 Python 端设置）
# fallback 到脚本同目录（向后兼容）
import os as _scene_os
_scene_data_env = _scene_os.environ.get("AICSS_SCENE_DATA_PATH", "")
if _scene_data_env and _scene_os.path.exists(_scene_data_env):
    scene_data = json.loads(open(_scene_data_env, encoding="utf-8").read())
else:
    scene_data = json.loads(open(os.path.join(os.path.dirname(__file__), "scene_data.json"), encoding="utf-8").read())


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


def make_paper_material(name, diffuse_path, normal_path, bevel_w, subsurface=0.15):
    """创建纸模材质（Principled BSDF + Image Texture，支持 RGBA 透明）。

    T12: 新增 ``subsurface`` 参数（默认 0.15），写入
    ``principled.inputs["Subsurface Weight"]``，让导出的 GLB 在其他
    viewer 里也有透纸感。
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    # 透明材质混合方式：
    #   - 'HASHED' 是最稳的 alpha 混合（避免深度排序问题，纸模有大量自交 plane）
    #   - 'BLEND' 用于需要软透明但会有 z-fighting
    #   - 'OPAQUE' 时 alpha 完全被忽略，diffuse RGBA 的 A 通道不参与合成
    # 前端 Three.js 渲染时 paper-diorama billboard 也是 transparent，这里必须保持一致。
    #
    # NOTE: `mat.shadow_method` 在 Blender 5.2 LTS 上被移除了——
    # ``AttributeError: 'Material' object has no attribute 'shadow_method'``。
    # 用 hasattr 守卫，保持向后兼容（旧版本仍能正确启用逐片段 alpha shadow）。
    mat.blend_method = 'HASHED'
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = 'HASHED'
    mat.alpha_threshold = 0.5  # HASHED 模式下低于此值的像素被剔除
    mat.use_backface_culling = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (400, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (0, 0)
    # 显式启用 Alpha 输入并把它默认设 1.0；如果 diffuse_path 提供的是 RGBA，
    # 下文会用 diffuse 纹理的 Alpha 通道覆盖。
    principled.inputs["Alpha"].default_value = 1.0
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    # T12 — SSS：写入 Subsurface Weight（Blender 4.x 输入名）
    if "Subsurface Weight" in principled.inputs:
        principled.inputs["Subsurface Weight"].default_value = float(subsurface)
    if "Subsurface Color" in principled.inputs:
        principled.inputs["Subsurface Color"].default_value = (1.0, 0.96, 0.9, 1.0)
    if "Subsurface Radius" in principled.inputs:
        principled.inputs["Subsurface Radius"].default_value = (0.1, 0.05, 0.02)

    if diffuse_path:
        try:
            img = bpy.data.images.load(diffuse_path)
            # RGBA 纹理必须用 sRGB 才能在 Base Color 阶段正确解码 RGB，
            # Alpha 通道不依赖 colorspace 但保留 RGBA 模式 → Alpha 输出才有意义。
            img.colorspace_settings.name = "sRGB"
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.location = (-400, 100)
            links.new(tex.outputs["Color"], principled.inputs["Base Color"])
            # 把同一张纹理的 Alpha 接到 Principled BSDF 的 Alpha 输入，
            # 这样 RGBA PNG 的透明区域（mask=0）真正参与混合，不再被 OPAQUE 覆盖。
            if 'Alpha' in tex.outputs:
                links.new(tex.outputs["Alpha"], principled.inputs["Alpha"])
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


def _load_thickness_texture(thick_path):
    """加载厚度纹理图，返回 (width, height, pixels) 或 None。"""
    if not thick_path:
        return None
    try:
        img = bpy.data.images.load(thick_path)
        if img.size[0] == 0 or img.size[1] == 0:
            return None
        # 转为 numpy 数组（像素按 Z 顺序排列）
        pixels = list(img.pixels)
        return (img.size[0], img.size[1], pixels)
    except Exception as exc:
        print("[WARN] Could not load thickness texture", thick_path, ":", exc)
        return None


def _sample_thickness(tex_data, u, v):
    """从厚度纹理采样，返回 0-1 范围的厚度值。"""
    if tex_data is None:
        return 0.5
    w, h, pixels = tex_data
    # 双线性插值
    px = u * (w - 1)
    py = v * (h - 1)
    x0, y0 = int(px), int(py)
    x1, y1 = min(x0 + 1, w - 1), min(y0 + 1, h - 1)
    fx, fy = px - x0, py - y0
    def _get(x, y):
        idx = (y * w + x) * 4
        return pixels[idx] if idx < len(pixels) else 0.0
    v00 = _get(x0, y0); v10 = _get(x1, y0)
    v01 = _get(x0, y1); v11 = _get(x1, y1)
    return (v00 * (1-fx) * (1-fy) + v10 * fx * (1-fy) +
            v01 * (1-fx) * fy     + v11 * fx * fy)


def make_displaced_plane(name, w, h, thickness, thick_path, segments=48):
    """
    创建基于厚度纹理的非均匀厚度平面 mesh。

    参数：
        segments: 平面网格分辨率（segments x segments 顶点）
        thickness: 最大厚度（灰度 255 时对应的世界单位厚度）
    """
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()

    tex_data = _load_thickness_texture(thick_path)

    # 生成顶点网格
    verts_grid = []
    for row in range(segments + 1):
        row_verts = []
        for col in range(segments + 1):
            u = col / segments
            v = row / segments
            local_x = (u - 0.5) * w
            local_y = (v - 0.5) * h

            # 采样厚度
            t_norm = _sample_thickness(tex_data, u, v)  # 0-1
            local_z = t_norm * thickness  # 0 到 max_thickness

            vert = bm.verts.new((local_x, local_y, local_z))
            row_verts.append(vert)
        verts_grid.append(row_verts)

    bm.verts.ensure_lookup_table()

    # 生成面
    for row in range(segments):
        for col in range(segments):
            v00 = verts_grid[row    ][col    ]
            v10 = verts_grid[row    ][col + 1]
            v11 = verts_grid[row + 1][col + 1]
            v01 = verts_grid[row + 1][col    ]
            try:
                bm.faces.new([v00, v10, v11, v01])
            except Exception:
                pass

    bm.to_mesh(mesh)
    bm.free()
    return mesh


def make_billboard_plane(name, w, h, d, layer_z, bevel_w, diff_path):
    """
    strip-stack billboard plane mesh — 带 UV 坐标的 2D 平面。

    billboard 语义：正对相机的平面（垂直于 Z 轴），有正确的 TEXCOORD_0 映射。
    厚度 d 仅用于 export_glb 的 bevel modifier，不影响几何体。
    """
    print("[DEBUG] make_billboard_plane called:", name, "diff_path=", repr(diff_path))
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    hw, hh = w / 2.0, h / 2.0
    v0 = bm.verts.new((-hw, -hh, 0))
    v1 = bm.verts.new(( hw, -hh, 0))
    v2 = bm.verts.new(( hw,  hh, 0))
    v3 = bm.verts.new((-hw,  hh, 0))
    face = bm.faces.new([v0, v1, v2, v3])
    uv_layer = bm.loops.layers.uv.verify()
    for loop in face.loops:
        uv = loop[uv_layer]
        if loop.vert is v0:
            uv.uv = (0.0, 0.0)
        elif loop.vert is v1:
            uv.uv = (1.0, 0.0)
        elif loop.vert is v2:
            uv.uv = (1.0, 1.0)
        elif loop.vert is v3:
            uv.uv = (0.0, 1.0)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = (0, 0, layer_z)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    if diff_path:
        try:
            mat = make_paper_material("Mat_" + name, diff_path, "", bevel_w)
            mesh.materials.append(mat)
        except Exception as exc:
            print("[WARN] billboard material failed", name, ":", exc)

    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width = bevel_w
    bevel.segments = 2
    bevel.limit_method = "ANGLE"

    return obj


def make_background_plane(bg):
    """
    strip-stack 最终 inpaint 背景的 BackgroundPlane mesh。
    大尺寸平面，z 极远，作为整个 3D 场景的最远景。
    带正确 UV 坐标。
    """
    name = "BackgroundPlane"
    w = bg.get("width", 30.0)
    h = bg.get("height", 20.0)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    hw, hh = w / 2.0, h / 2.0
    v0 = bm.verts.new((-hw, -hh, 0))
    v1 = bm.verts.new(( hw, -hh, 0))
    v2 = bm.verts.new(( hw,  hh, 0))
    v3 = bm.verts.new((-hw,  hh, 0))
    face = bm.faces.new([v0, v1, v2, v3])
    uv_layer = bm.loops.layers.uv.verify()
    for loop in face.loops:
        uv = loop[uv_layer]
        if loop.vert is v0:
            uv.uv = (0.0, 0.0)
        elif loop.vert is v1:
            uv.uv = (1.0, 0.0)
        elif loop.vert is v2:
            uv.uv = (1.0, 1.0)
        elif loop.vert is v3:
            uv.uv = (0.0, 1.0)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj.location = (0, 0, bg.get("z", -25.0))
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj

    diff_path = bg.get("texture", "") or ""
    if diff_path:
        try:
            mat = make_paper_material("Mat_" + name, diff_path, "", bg.get("bevel_width", 0.005))
            mesh.materials.append(mat)
        except Exception as exc:
            print("[WARN] background material failed:", exc)

    return obj


# ── 构建层 Meshes ─────────────────────────────────────────────────────────────
for layer in scene_data.get("layers", []):
    w = layer.get("width", 20.0)
    h = layer.get("height", 15.0)
    d = layer.get("thickness", 0.1)
    z_pos = layer.get("position_z", 0.0)
    bevel_w = layer.get("bevel_width", 0.005)
    diff_path = layer.get("diffuse_texture", "") or ""
    norm_path = layer.get("normal_texture", "") or ""
    thick_path = layer.get("thickness_texture", "") or ""
    use_disp = layer.get("use_displacement", False)

    if diff_path and diff_path.startswith("data:"):
        diff_path = ""
    if norm_path and norm_path.startswith("data:"):
        norm_path = ""
    if thick_path and thick_path.startswith("data:"):
        thick_path = ""

    layer_key = str(layer.get("layer_key", "layer"))

    # 根据 use_displacement 选择网格生成方式
    if use_disp and thick_path:
        mesh = make_displaced_plane("Layer_" + layer_key, w, h, d, thick_path, segments=48)
    else:
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


# ── 构建 strip-stack Billboard Meshes ─────────────────────────────────────────
for bb in scene_data.get("strip_billboards", []):
    diff_path = bb.get("diffuse_texture", "") or ""
    if diff_path.startswith("data:"):
        diff_path = ""
    rid = str(bb.get("region_id", "strip"))
    name = "RegionMesh_" + rid
    make_billboard_plane(
        name,
        bb.get("width", 20.0),
        bb.get("height", 15.0),
        bb.get("thickness", 0.20),
        bb.get("layer_z", -2.0),
        bb.get("bevel_width", 0.005),
        diff_path,
    )


# ── 构建 strip-stack BackgroundPlane Mesh ─────────────────────────────────────
bg = scene_data.get("background_plane")
if bg:
    make_background_plane(bg)


# ── T14 构建灯光 ─────────────────────────────────────────────────────────────
def make_light(role, spec):
    """根据 manifest.lighting 的 spec 创建一盏灯。

    spec 字段（双花括号是因为整段脚本经 str.format 渲染）：
        {{type, energy, color, location, rotation, size}}
    type: SUN / AREA / SPOT / POINT
    """
    light_type = str(spec.get("type", "SUN")).upper()
    if light_type not in ("SUN", "AREA", "SPOT", "POINT"):
        return None
    light_data = bpy.data.lights.new(name="AICSS_Light_" + role, type=light_type)
    light_data.energy = float(spec.get("energy", 1.0))
    color = spec.get("color", [1.0, 1.0, 1.0])
    light_data.color = (float(color[0]), float(color[1]), float(color[2]))
    if "size" in spec:
        try:
            light_data.size = float(spec["size"])
        except Exception:
            pass

    light_obj = bpy.data.objects.new("AICSS_Light_" + role + "_" + light_type, light_data)
    bpy.context.scene.collection.objects.link(light_obj)

    loc = spec.get("location")
    if isinstance(loc, (list, tuple)) and len(loc) >= 3:
        light_obj.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    else:
        # role 默认位置（与插件 add_lighting operator 一致）
        if role == "key":
            light_obj.location = (8.0, -8.0, 12.0)
        elif role == "fill":
            light_obj.location = (-8.0, -6.0, 8.0)
        elif role == "rim":
            light_obj.location = (0.0, 8.0, 10.0)

    rot = spec.get("rotation")
    if isinstance(rot, (list, tuple)) and len(rot) >= 3:
        light_obj.rotation_euler = (float(rot[0]), float(rot[1]), float(rot[2]))

    light_obj["aicss_role"] = "light_" + role
    return light_obj


lighting = scene_data.get("lighting") or {{}}
include_lights = bool(scene_data.get("include_lights", True))
created_lights = 0
if include_lights and isinstance(lighting, dict):
    for role in ("key", "fill", "rim"):
        spec = lighting.get(role)
        if not spec or not isinstance(spec, dict):
            continue
        obj = make_light(role, spec)
        if obj is not None:
            created_lights += 1
print("[OK] Created %d lights" % created_lights)


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
        export_normals=True,
        export_texcoords=True,
        export_apply=True,
        export_lights={export_lights},
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

# ── 统计 mesh 数据 ─────────────────────────────────────────────────────────────
total_vertices = 0
total_faces = 0
object_count = 0
for obj in bpy.context.scene.objects:
    if obj.type != "MESH":
        continue
    object_count += 1
    mesh = obj.data
    # 累加 vertices / polygons（polygons = face count）
    total_vertices += len(mesh.vertices)
    total_faces += len(mesh.polygons)

# 把统计写到 output_path 同目录下，供 Python 读取
import os as _stats_os
import json as _stats_json
_stats_dir = _stats_os.path.dirname(output_path) or "."
_stats_path = _stats_os.path.join(_stats_dir, "mesh_stats.json")
try:
    with open(_stats_path, "w", encoding="utf-8") as _f:
        _stats_json.dump(
            {{
                "object_count": object_count,
                "vertex_count": total_vertices,
                "face_count": total_faces,
            }},
            _f,
        )
except Exception as _e:
    print("[WARN] failed to write mesh_stats:", _e)

print("[OK] Exported to %s vertices=%d faces=%d objects=%d" % (output_path, total_vertices, total_faces, object_count))
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
        export_lights="True" if (scene.include_lights and scene.lighting) else "False",
    )


def _serialize_scene_for_blender(scene: SceneExportData) -> str:
    """将 SceneExportData 序列化为 JSON 供 Blender 脚本内联读取。"""
    data = {
        "scene_id": scene.scene_id,
        "scene_width": scene.scene_width,
        "scene_height": scene.scene_height,
        "layers": [],
        "objects": [],
        "strip_billboards": [],
        "background_plane": None,
        # T14 — 灯光（dict 格式 {key, fill, rim}）
        "lighting": scene.lighting or {},
        "include_lights": bool(scene.include_lights),
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
            "thickness_texture": layer.thickness_texture or "",
            "outlined_texture": layer.outlined_texture or "",
            "bevel_width": layer.bevel_width,
            "depth_value": layer.depth_value,
            "use_displacement": layer.use_displacement,
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

    for bb in scene.strip_billboards:
        data["strip_billboards"].append({
            "region_id": bb.region_id,
            "depth_layer_key": bb.depth_layer_key,
            "depth_value": bb.depth_value,
            "color_index": bb.color_index,
            "layer_z": bb.layer_z,
            "width": bb.width,
            "height": bb.height,
            "thickness": bb.thickness,
            "diffuse_texture": bb.diffuse_texture or "",
            "layer_polygon": bb.layer_polygon or [],
            "bevel_width": bb.bevel_width,
        })

    if scene.background_plane:
        data["background_plane"] = {
            "texture": scene.background_plane.texture or "",
            "width": scene.background_plane.width,
            "height": scene.background_plane.height,
            "z": scene.background_plane.z,
            "bevel_width": scene.background_plane.bevel_width,
        }

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

    # strip-stack billboards
    for billboard in scene.strip_billboards:
        url = billboard.diffuse_texture
        if url and url.startswith("data:"):
            saved = _download_base64_image(url, texture_dir)
            if saved:
                billboard.diffuse_texture = saved

    # background plane
    if scene.background_plane and scene.background_plane.texture:
        url = scene.background_plane.texture
        if url.startswith("data:"):
            saved = _download_base64_image(url, texture_dir)
            if saved:
                scene.background_plane.texture = saved

    return texture_dir


# ─────────────────────────────────────────────────────────────────────────────
# 动态超时计算
# ─────────────────────────────────────────────────────────────────────────────


def _calculate_export_timeout(scene: SceneExportData) -> int:
    """
    根据场景复杂度动态计算 Blender 导出超时时间。

    估算依据：
    - 基础时间：60s（Blender 启动 + 场景构建）
    - 每个物体：+5s
    - 每个层级：+10s
    - 纹理数量：+15s per texture
    - FBX 格式：额外 +30s（导出更慢）
    - 上限：300s（5分钟）

    简单场景（4层无纹理）：~100s
    复杂场景（20物体 + 纹理）：~300s
    """
    base_timeout = 60

    object_count = len(scene.objects)
    layer_count = len(scene.layers)
    texture_count = 0

    for layer in scene.layers:
        for attr in [layer.diffuse_texture, layer.normal_texture, layer.thickness_texture]:
            if attr and not attr.startswith("data:"):
                texture_count += 1

    for obj in scene.objects:
        for attr in [obj.diffuse_texture, obj.normal_texture, obj.thickness_texture]:
            if attr and not attr.startswith("data:"):
                texture_count += 1

    for bb in scene.strip_billboards:
        if bb.diffuse_texture and not bb.diffuse_texture.startswith("data:"):
            texture_count += 1

    if scene.background_plane and scene.background_plane.texture and not scene.background_plane.texture.startswith("data:"):
        texture_count += 1

    estimated = (
        base_timeout
        + object_count * 5
        + layer_count * 10
        + texture_count * 15
        + len(scene.strip_billboards) * 8
        + (10 if scene.background_plane else 0)
        + (30 if scene.output_format == "fbx" else 0)
    )

    # 至少 60s，最多 300s
    return min(300, max(60, estimated))


# ─────────────────────────────────────────────────────────────────────────────
# 核心导出函数
# ─────────────────────────────────────────────────────────────────────────────


def _read_mesh_stats(stats_path: Path) -> tuple[int, int, int]:
    """Read mesh_stats.json written by the Blender script.

    Returns (object_count, vertex_count, face_count). Falls back to zeros
    if the file is missing or unreadable.
    """
    try:
        if stats_path.exists():
            data = json.loads(stats_path.read_text(encoding="utf-8"))
            return (
                int(data.get("object_count", 0)),
                int(data.get("vertex_count", 0)),
                int(data.get("face_count", 0)),
            )
    except Exception:
        logger.warning("[mesh_exporter] failed to read mesh_stats.json at %s", stats_path)
    return 0, 0, 0


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
            object_count=len(scene.objects) + len(scene.strip_billboards) + (1 if scene.background_plane else 0),
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

        # Write scene data as a JSON file alongside the script so Blender can
        # load it without worrying about string-escaping the embedded JSON.
        scene_json_path = tmp_path / "scene_data.json"
        scene_json_path.write_text(_serialize_scene_for_blender(scene), encoding="utf-8")

        out_dir = Path(output_dir) if output_dir else tmp_path
        out_dir.mkdir(parents=True, exist_ok=True)
        output_file = out_dir / f"{scene.scene_id}.{ext}"

        # 动态计算超时
        timeout_seconds = _calculate_export_timeout(scene)
        logger.info(f"[mesh_exporter] Estimated timeout: {timeout_seconds}s "
                    f"(objects={len(scene.objects)}, layers={len(scene.layers)}, format={fmt})")

        try:
            env = os.environ.copy()
            env["AICSS_SCENE_DATA_PATH"] = str(scene_json_path)
            result = subprocess.run(
                [blender_path, "--background", "--python", str(script_path), "--", str(output_file)],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )

            # Always dump Blender stdout/stderr next to the GLB so we can
            # diagnose "GLB came out empty / no textures / etc." without
            # rerunning the whole pipeline. Without this, exit 0 swallows
            # every diagnostic the Blender script emitted (e.g. ``[DEBUG]
            # make_billboard_plane``), and silent corruption is hard to spot.
            try:
                debug_log = tmp_path / "blender.log"
                debug_log.write_text(
                    f"--- stdout ---\n{result.stdout}\n\n--- stderr ---\n{result.stderr}\n",
                    encoding="utf-8",
                )
                logger.info(f"[mesh_exporter] blender log: {debug_log}")
            except Exception as _dump_err:
                logger.warning(f"[mesh_exporter] failed to dump blender log: {_dump_err}")

            if result.returncode != 0:
                return MeshExportResult(
                    mesh_id=scene.scene_id,
                    scene_id=scene.scene_id,
                    file_path=str(output_file),
                    file_size=0,
                    file_sha256="",
                    format=fmt,
                    object_count=len(scene.objects) + len(scene.strip_billboards) + (1 if scene.background_plane else 0),
                    vertex_count=sum(len(o.vertices) for o in scene.objects),
                    face_count=sum(len(o.faces) for o in scene.objects),
                    success=False,
                    error=f"Blender export failed (exit {result.returncode}): {result.stderr[:500]}",
                )

            if not output_file.exists() or output_file.stat().st_size == 0:
                return MeshExportResult(
                    mesh_id=scene.scene_id,
                    scene_id=scene.scene_id,
                    file_path=str(output_file),
                    file_size=0,
                    file_sha256="",
                    format=fmt,
                    object_count=len(scene.objects) + len(scene.strip_billboards) + (1 if scene.background_plane else 0),
                    vertex_count=sum(len(o.vertices) for o in scene.objects),
                    face_count=sum(len(o.faces) for o in scene.objects),
                    success=False,
                    error="Blender completed but output file not found or empty",
                )

            file_bytes = output_file.read_bytes()
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()

            stats_path = output_file.parent / "mesh_stats.json"
            obj_count, vert_count, face_count = _read_mesh_stats(stats_path)

            logger.info(
                f"[mesh_exporter] Exported {output_file} "
                f"({output_file.stat().st_size:,} bytes, "
                f"{obj_count} objects, {vert_count} verts, {face_count} faces)"
            )

            # 把 GLB 复制到持久化目录（避免 tempfile.TemporaryDirectory 在 with 块退出后清理）
            persist_root = Path(os.environ.get("AICSS_MESH_PERSIST_DIR", str(Path(tempfile.gettempdir()) / "aicss_mesh_persist")))
            try:
                persist_root.mkdir(parents=True, exist_ok=True)
                persist_file = persist_root / output_file.name
                persist_file.write_bytes(file_bytes)
                persist_path = str(persist_file)
            except Exception as pe:
                logger.warning(f"[mesh_exporter] failed to persist GLB to {persist_root}: {pe}")
                persist_path = str(output_file)

            # Keep the Blender debug log alongside the persisted GLB so the
            # next session can grep it without rerunning the export.
            try:
                debug_log_src = tmp_path / "blender.log"
                if debug_log_src.exists():
                    persist_log = persist_root / f"{scene.scene_id}.blender.log"
                    persist_log.write_bytes(debug_log_src.read_bytes())
                    logger.info(f"[mesh_exporter] blender log persisted: {persist_log}")
            except Exception as _le:
                logger.warning(f"[mesh_exporter] failed to persist blender log: {_le}")

            return MeshExportResult(
                mesh_id=scene.scene_id,
                scene_id=scene.scene_id,
                file_path=persist_path,
                file_size=output_file.stat().st_size,
                file_sha256=sha256_hash,
                format=fmt,
                object_count=obj_count,
                vertex_count=vert_count,
                face_count=face_count,
                success=True,
            )

        except subprocess.TimeoutExpired:
            return MeshExportResult(
                mesh_id=scene.scene_id,
                scene_id=scene.scene_id,
                file_path=str(output_file),
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=len(scene.objects) + len(scene.strip_billboards) + (1 if scene.background_plane else 0),
                vertex_count=sum(len(o.vertices) for o in scene.objects),
                face_count=sum(len(o.faces) for o in scene.objects),
                success=False,
                error=f"Blender export timed out after {timeout_seconds} seconds",
            )
        except FileNotFoundError:
            return MeshExportResult(
                mesh_id=scene.scene_id,
                scene_id=scene.scene_id,
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=len(scene.objects) + len(scene.strip_billboards) + (1 if scene.background_plane else 0),
                vertex_count=sum(len(o.vertices) for o in scene.objects),
                face_count=sum(len(o.faces) for o in scene.objects),
                success=False,
                error=f"Blender executable not found at: {blender_path}",
            )
        except Exception as e:
            return MeshExportResult(
                mesh_id=scene.scene_id,
                scene_id=scene.scene_id,
                file_path="",
                file_size=0,
                file_sha256="",
                format=fmt,
                object_count=len(scene.objects) + len(scene.strip_billboards) + (1 if scene.background_plane else 0),
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

        depth_value = asset.get("depthValue")
        use_displacement = bool(asset.get("thicknessGrayUrl"))
        fine_z = _compute_fine_z_offset(depth_value, z_pos)

        layer_data = LayerMeshData(
            layer_key=layer_key,
            layer_name=f"Depth Layer: {layer_key}",
            width=20.0,
            height=15.0,
            thickness=_layer_thickness(layer_key),
            position_z=fine_z,
            diffuse_texture=asset.get("rgbaUrl") or asset.get("paperStyleUrl"),
            normal_texture=asset.get("normalMapUrl"),
            thickness_texture=asset.get("thicknessGrayUrl"),
            outlined_texture=asset.get("outlinedUrl"),
            depth_value=depth_value,
            use_displacement=use_displacement,
        )
        scene.layers.append(layer_data)

    return export_scene(scene, output_dir, output_format)


def export_full_scene(
    analysis_result: dict,
    depth_split_result: dict,
    layer_assets: dict,
    object_assets: dict,
    billboard_offsets: dict,
    strip_stack: Optional[list[dict]] = None,
    regions: Optional[list[dict]] = None,
    scene_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "glb",
    include_textures: bool = True,
) -> MeshExportResult:
    """导出完整场景（层 + 物体 + 可选 strip-stack / regions billboards + 背景平面）。"""
    scene = build_scene_from_frontend_data(
        analysis_result=analysis_result,
        depth_split_result=depth_split_result,
        layer_assets=layer_assets,
        object_assets=object_assets,
        billboard_offsets=billboard_offsets,
        scene_id=scene_id or f"scene_{uuid.uuid4().hex[:8]}",
    )

    # 叠加 strip-stack billboards + 背景平面（在原 layers/objects 之上）
    if strip_stack:
        _populate_strip_stack_into_scene(scene, strip_stack)

    # 叠加用户自由选区 regions → PlaneGeometry（按 depthValue 精细 Z）
    if regions:
        _populate_regions_into_scene(scene, regions)

    scene.output_format = output_format
    scene.include_textures = include_textures
    return export_scene(scene, output_dir, output_format)


_LAYER_Z_TABLE = {
    "foreground": -2.0,
    "midground": -6.0,
    "background": -12.0,
    "sky": -20.0,
}


def _parse_depth_value(raw) -> int:
    if raw is None:
        return 128
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 128


def _billboard_from_region_like(
    *,
    region_id: str,
    depth_layer_key: str,
    depth_value: int,
    color_index: int,
    diffuse_texture: Optional[str],
    layer_polygon: Optional[list],
    z_nudge: float = 0.0,
) -> StripBillboardData:
    """把 strip step / LayerRegion 统一转成 StripBillboardData。"""
    base_z = _LAYER_Z_TABLE.get(depth_layer_key, -2.0)
    layer_z = _compute_fine_z_offset(float(depth_value), base_z) + z_nudge
    polygon = layer_polygon if isinstance(layer_polygon, list) else None
    return StripBillboardData(
        region_id=str(region_id),
        depth_layer_key=depth_layer_key,
        depth_value=depth_value,
        color_index=color_index,
        layer_z=layer_z,
        width=20.0,
        height=15.0,
        thickness=_billboard_thickness(depth_layer_key),
        diffuse_texture=diffuse_texture,
        layer_polygon=polygon,
        bevel_width=0.005,
    )


def _populate_strip_stack_into_scene(scene: SceneExportData, strip_stack: list[dict]) -> None:
    """
    把前端的 stripStack 数组填进 SceneExportData.strip_billboards + background_plane。

    每条 step 的 billboardUrl 成为一个 StripBillboardData;
    最后一条 step 的 inpaintResultUrl 成为 BackgroundPlaneData.texture。
    若 stripStack 只有一条且无 billboardUrl，则跳过（仅保留背景平面）;
    全部无 billboardUrl 时直接 return（保护现状）。
    """
    if not strip_stack:
        return

    billboards: list[StripBillboardData] = []
    for i, step in enumerate(strip_stack):
        if not isinstance(step, dict):
            continue
        billboard_url = step.get("billboardUrl")
        if not billboard_url:
            continue
        depth_layer_key = step.get("depthLayer") or "foreground"
        depth_value_int = _parse_depth_value(step.get("depthValue"))
        region_id = step.get("regionId") or f"strip_{i}"
        try:
            color_index = int(step.get("colorIndex", i))
        except (TypeError, ValueError):
            color_index = i
        billboards.append(
            _billboard_from_region_like(
                region_id=str(region_id),
                depth_layer_key=depth_layer_key,
                depth_value=depth_value_int,
                color_index=color_index,
                diffuse_texture=billboard_url,
                layer_polygon=step.get("layerPolygon"),
                z_nudge=0.02 * i,  # 防 z-fighting
            )
        )

    scene.strip_billboards = billboards

    # 最后一条 step 的 inpaintResultUrl 作为背景平面
    last_step = strip_stack[-1] if strip_stack else None
    if isinstance(last_step, dict):
        inpaint_url = last_step.get("inpaintResultUrl")
        if inpaint_url:
            scene.background_plane = BackgroundPlaneData(texture=inpaint_url)


def _populate_regions_into_scene(scene: SceneExportData, regions: list[dict]) -> None:
    """
    把前端 LayerRegion[] 转为 PlaneGeometry billboards，按 depthValue 精细 Z 定位。

    每项期望字段：id, polygon, depthLayer, colorIndex, depthValue；
    可选 billboardUrl（前端从 billboardAssets 合并）。无纹理时仍导出平面。
    已存在的 strip_billboards（来自 strip_stack）会被追加，不覆盖。
    """
    if not regions:
        return

    existing_ids = {bb.region_id for bb in scene.strip_billboards}
    offset = len(scene.strip_billboards)

    for i, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        region_id = str(region.get("id") or region.get("regionId") or f"region_{i}")
        # 与 strip_stack 同源 region 去重，避免双份 mesh
        if region_id in existing_ids:
            continue

        depth_layer_key = region.get("depthLayer") or region.get("depth_layer") or "foreground"
        depth_value_int = _parse_depth_value(region.get("depthValue", region.get("depth_value")))
        try:
            color_index = int(region.get("colorIndex", region.get("color_index", i)))
        except (TypeError, ValueError):
            color_index = i

        polygon = region.get("polygon") or region.get("layerPolygon")
        billboard_url = (
            region.get("billboardUrl")
            or region.get("billboard_url")
            or region.get("rgbaUrl")
        )

        scene.strip_billboards.append(
            _billboard_from_region_like(
                region_id=region_id,
                depth_layer_key=str(depth_layer_key),
                depth_value=depth_value_int,
                color_index=color_index,
                diffuse_texture=billboard_url,
                layer_polygon=polygon,
                z_nudge=0.02 * (offset + i),
            )
        )
        existing_ids.add(region_id)


def export_strip_stack_only(
    strip_stack: list[dict],
    scene_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    output_format: str = "glb",
    include_textures: bool = True,
) -> MeshExportResult:
    """
    便捷封装：仅导出 strip-stack billboards + 背景平面（不导 layers/objects）。
    """
    scene = SceneExportData(
        scene_id=scene_id or f"strip_stack_{uuid.uuid4().hex[:8]}",
        output_format=output_format,
        include_textures=include_textures,
    )
    _populate_strip_stack_into_scene(scene, strip_stack)
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
