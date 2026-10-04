"""
paper_material — Phase 1 v1 node graph for the AICSS paper-diorama look.

Spec (per Implementation Plan §1.2.5 / §2.1.1):

    v1 (Phase 1):
        ImageTexture → ColorRamp (cartoonisation) → Principled BSDF (Base Color)
        ImageTexture → Normal Map → Principled BSDF (Normal)
        Principled BSDF: Roughness=0.9, Specular=0.0

    v2 (Phase 2) — added later, this module is forward-compatible:
        + Procedural Noise → ColorRamp → Principled BSDF (Normal) for paper fibre
        + Subsurface Scattering: 0.15, Subsurface Color #FFF5E6
        + Subsurface IOR 1.4, Subsurface Radius (0.1, 0.05, 0.02)

The function ``apply_paper_material`` is callable from any operator and
creates a ``PaperMaterial`` data-block if one doesn't exist, then assigns
it to the mesh object. The node graph is idempotent — calling it twice
on the same object reuses the existing material.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    import bpy
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False


# Canonical material name — re-using this across objects lets us tweak
# the node graph once and have it propagate everywhere.
PAPER_MATERIAL_NAME = "AICSS_PaperMaterial"


@dataclass
class PaperMaterialParams:
    """Tunable parameters for the paper material.

    v1 字段（Phase 1）保持默认；v2 字段（Phase 2，T12）：
        subsurface: 0.15（默认开启 SSS，逆光透纸感）
        subsurface_color: (1.0, 0.96, 0.9) 暖白
        subsurface_radius: (0.1, 0.05, 0.02) 红绿蓝扩散半径
        use_fibre: False（默认关；开则叠加细密噪声到 Normal）
    """
    roughness: float = 0.9
    specular: float = 0.0
    color_levels: int = 12     # k-means cartoonisation cluster count
    normal_strength: float = 0.8
    # T12 — SSS（默认 0.15，让逆光边缘有透纸感）
    subsurface: float = 0.15
    subsurface_color: tuple = (1.0, 0.96, 0.9)
    subsurface_radius: tuple = (0.1, 0.05, 0.02)
    # T12 — 纤维法线（默认关；开则 Noise → ColorRamp → 叠加到 Normal）
    use_fibre: bool = False
    fibre_scale: float = 50.0   # Noise 纹理频率，越大越细密
    fibre_strength: float = 0.3  # 纤维法线叠加强度（0-1）


def build_paper_node_graph(material, *, image_path: Optional[str] = None,
                            params: Optional[PaperMaterialParams] = None):
    """Populate ``material``'s node tree with the AICSS paper node graph.

    Idempotent — removes any existing AICSS_* nodes first so repeated
    calls don't accumulate duplicates. ``params`` defaults to ``PaperMaterialParams()``.
    """
    if not _HAS_BPY:
        return
    if params is None:
        params = PaperMaterialParams()

    material.use_nodes = True
    # blend_method / 透明度由 apply_paper_material 根据贴图 alpha 通道决定
    tree = material.node_tree
    nodes = tree.nodes

    # 清掉所有节点（包括 Blender 默认创建的 Principled BSDF / Material Output），
    # 否则默认 Material Output 会连到没纹理的默认 BSDF，AICSS 的节点图被忽略。
    for node in list(nodes):
        nodes.remove(node)

    # ── Core nodes ──────────────────────────────────────────────────────────
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.name = "AICSS_Output"
    output.location = (800, 0)

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.name = "AICSS_BSDF"
    bsdf.location = (400, 0)
    bsdf.inputs['Roughness'].default_value = params.roughness
    # Blender 4.x+ renamed 'Specular' → 'Specular IOR Level'; handle both
    _spec_input = bsdf.inputs.get('Specular') or bsdf.inputs.get('Specular IOR Level')
    if _spec_input is not None:
        _spec_input.default_value = params.specular
    # Phase 1 v1：关闭 SSS（EEVEE 下 Subsurface Weight>0 会让贴图颜色被吞掉，
    # 整个平面渲染成灰阶）。SSS 留到 Phase 2 Cycles 下再开。
    if 'Subsurface Weight' in bsdf.inputs:
        bsdf.inputs['Subsurface Weight'].default_value = 0.0

    # Link BSDF → Output
    tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    # ── Diffuse texture (Phase 1 v1) ────────────────────────────────────────
    if image_path:
        tex = nodes.new(type='ShaderNodeTexImage')
        tex.name = "AICSS_DiffuseTex"
        tex.location = (-600, 200)
        try:
            tex.image = _load_image(image_path)
        except Exception:
            tex.image = None
        # Phase 1 v1：直接把贴图 Color 接到 BSDF Base Color。
        # ColorRamp cartoonisation 会把 RGB 当 luminance 输出灰阶，反而失真，
        # 留到 Phase 2 用更合适的色阶分离节点再做。
        tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        # 保留 Alpha → BSDF Alpha（支持抠绿后的 RGBA PNG）
        if 'Alpha' in bsdf.inputs:
            tree.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])

    # ── Normal map (Phase 1 v1) ─────────────────────────────────────────────
    # Phase 1: we look for a sibling ``*_normal.png`` next to the diffuse
    # PNG. Phase 2 will switch to the manifest's normalMapUrl field.
    normal_path = _sibling_normal(image_path) if image_path else None
    normal_node = None
    if normal_path:
        ntex = nodes.new(type='ShaderNodeTexImage')
        ntex.name = "AICSS_NormalTex"
        ntex.location = (-600, -200)
        try:
            ntex.image = _load_image(normal_path)
        except Exception:
            ntex.image = None
        ntex.image.colorspace_settings.name = 'Non-Color'

        normal_node = nodes.new(type='ShaderNodeNormalMap')
        normal_node.name = "AICSS_NormalMap"
        normal_node.location = (-100, -200)
        normal_node.inputs['Strength'].default_value = params.normal_strength

        tree.links.new(ntex.outputs['Color'], normal_node.inputs['Color'])

    # ── T12 纤维分支：Noise → ColorRamp → 叠加到 Normal（NormalMap 之前混合） ──
    if params.use_fibre:
        noise = nodes.new(type='ShaderNodeTexNoise')
        noise.name = "AICSS_FibreNoise"
        noise.location = (-900, -400)
        noise.inputs['Scale'].default_value = params.fibre_scale
        # 高细节，少大尺度变化
        noise.inputs['Detail'].default_value = 8.0
        noise.inputs['Roughness'].default_value = 0.6

        fibre_ramp = nodes.new(type='ShaderNodeValToRGB')
        fibre_ramp.name = "AICSS_FibreRamp"
        fibre_ramp.location = (-600, -400)
        # 让噪声映射到 0.4-0.6 范围，避免法线过度扭曲
        _populate_fibre_ramp(fibre_ramp)

        tree.links.new(noise.outputs['Fac'], fibre_ramp['Fac'] if 'Fac' in fibre_ramp.inputs else fibre_ramp.inputs['Fac'])

        # 把纤维噪声当作"切线空间法线"通过 NormalMap 节点叠加
        fibre_nmap = nodes.new(type='ShaderNodeNormalMap')
        fibre_nmap.name = "AICSS_FibreNormalMap"
        fibre_nmap.location = (-300, -400)
        fibre_nmap.inputs['Strength'].default_value = params.fibre_strength
        tree.links.new(fibre_ramp.outputs['Color'], fibre_nmap.inputs['Color'])

        # 混合纤维法线 + 主法线（若有），否则直接用纤维法线
        if normal_node is not None:
            mix = nodes.new(type='ShaderNodeMix')
            mix.name = "AICSS_NormalMix"
            mix.location = (100, -300)
            mix.data_type = 'VECTOR'
            mix.inputs['Factor'].default_value = 0.5
            mix.blend_type = 'MIX'
            tree.links.new(normal_node.outputs['Normal'], mix.inputs[6])  # A
            tree.links.new(fibre_nmap.outputs['Normal'], mix.inputs[7])   # B
            tree.links.new(mix.outputs[2], bsdf.inputs['Normal'])         # Result
        else:
            tree.links.new(fibre_nmap.outputs['Normal'], bsdf.inputs['Normal'])
    elif normal_node is not None:
        tree.links.new(normal_node.outputs['Normal'], bsdf.inputs['Normal'])


def apply_paper_material(obj, *, image_path: Optional[str] = None,
                          roughness: float = 0.9,
                          normal_strength: float = 0.8,
                          subsurface: float = 0.15,
                          use_fibre: bool = False) -> None:
    """Assign the paper material to ``obj``.

    Looks up the canonical AICSS_PaperMaterial data-block (creating it on
    first use) and assigns it to all mesh slots. ``image_path`` is
    forwarded to the diffuse texture node when provided.

    T12: 新增 ``subsurface`` / ``use_fibre`` 参数，传给 PaperMaterialParams。
    """
    if not _HAS_BPY:
        return
    # 每个对象用独立材质，否则共用一个材质时后调用的 image 会覆盖前面的。
    # 材质名按对象名 + 图名生成，保证唯一且可复用。
    img_base = os.path.splitext(os.path.basename(image_path))[0] if image_path else "notex"
    mat_name = f"{PAPER_MATERIAL_NAME}_{obj.name}_{img_base}"
    material = bpy.data.materials.get(mat_name)
    if material is None:
        material = bpy.data.materials.new(mat_name)

    params = PaperMaterialParams(
        roughness=roughness,
        normal_strength=normal_strength,
        subsurface=subsurface,
        use_fibre=use_fibre,
    )
    build_paper_node_graph(material, image_path=image_path, params=params)

    # 根据贴图是否有 alpha 通道选择 blend 模式：
    #   - 有 alpha（抠绿角色帧）→ BLEND，双面渲染，支持透明
    #   - 无 alpha（场景层 PNG）→ OPAQUE，避免 Cycles 透明排序问题
    try:
        has_alpha = False
        if image_path:
            for img in bpy.data.images:
                if img.filepath and os.path.exists(bpy.path.abspath(img.filepath)):
                    if os.path.basename(img.filepath) == os.path.basename(image_path):
                        has_alpha = (img.depth == 32)
                        break
        material.blend_method = 'BLEND' if has_alpha else 'OPAQUE'
        material.use_backface_culling = False
        if has_alpha:
            material.show_transparent_back = False
    except Exception:
        pass

    # Assign the material to every face-slot on the mesh
    if not obj.data.materials:
        obj.data.materials.append(material)
    else:
        for slot_idx in range(len(obj.data.materials)):
            obj.data.materials[slot_idx] = material


# ── Helpers (private) ──────────────────────────────────────────────────────────

def _load_image(path):
    """Load an image into Blender's bpy.data.images (reused if already loaded)."""
    if not _HAS_BPY:
        return None
    base = os.path.basename(path)
    for candidate in bpy.data.images:
        if candidate.filepath == path or candidate.name == base:
            return candidate
    try:
        return bpy.data.images.load(path)
    except Exception:
        return None


def _populate_color_ramp(ramp_node, color_levels: int) -> None:
    """Populate a ColorRamp node with discrete stops for cartoonisation.

    ``color_levels`` controls how many distinct colour bands the ramp has —
    fewer bands = flatter / more posterised look.
    """
    if not _HAS_BPY:
        return
    elements = getattr(ramp_node, "elements", None)
    if elements is None:
        return
    while len(elements) > 0:
        elements.remove(elements[0])
    color_levels = max(2, min(int(color_levels), 30))
    for i in range(color_levels):
        pos = i / (color_levels - 1) if color_levels > 1 else 0.5
        elem = elements.new(pos)
        elem.color = (pos, pos, pos, 1.0)


def _populate_fibre_ramp(ramp_node) -> None:
    """Populate a ColorRamp for paper-fibre normal: 把噪声映射到 0.4-0.6
    范围，避免法线过度扭曲（中心 0.5 = 平面法线）。
    """
    if not _HAS_BPY:
        return
    elements = getattr(ramp_node, "elements", None)
    if elements is None:
        return
    while len(elements) > 0:
        elements.remove(elements[0])
    # 两个 stop：0 → (0.4,0.4,0.4,1)，1 → (0.6,0.6,0.6,1)
    e0 = elements.new(0.0)
    e0.color = (0.4, 0.4, 0.4, 1.0)
    e1 = elements.new(1.0)
    e1.color = (0.6, 0.6, 0.6, 1.0)


def _sibling_normal(diffuse_path: str) -> Optional[str]:
    """If ``diffuse_path`` is ``layer_foreground.png``, return
    ``layer_foreground_normal.png`` if that file exists."""
    if not diffuse_path:
        return None
    stem, ext = os.path.splitext(diffuse_path)
    normal = f"{stem}_normal{ext}"
    return normal if os.path.exists(normal) else None