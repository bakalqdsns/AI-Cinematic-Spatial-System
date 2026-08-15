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

    All fields default to the v1 spec; Phase 2 will add SSS / fibre knobs.
    """
    roughness: float = 0.9
    specular: float = 0.0
    color_levels: int = 12     # k-means cartoonisation cluster count
    normal_strength: float = 0.8
    subsurface: float = 0.0    # 0.0 in Phase 1, 0.15 in Phase 2
    use_fibre: bool = False    # Phase 2 — procedural paper-fibre normal


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
    tree = material.node_tree
    nodes = tree.nodes

    # Wipe pre-existing AICSS_* nodes so the graph is rebuilt cleanly.
    for node in list(nodes):
        if node.name.startswith("AICSS_"):
            nodes.remove(node)

    # ── Core nodes ──────────────────────────────────────────────────────────
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.name = "AICSS_Output"
    output.location = (800, 0)

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.name = "AICSS_BSDF"
    bsdf.location = (400, 0)
    bsdf.inputs['Roughness'].default_value = params.roughness
    bsdf.inputs['Specular'].default_value = params.specular
    bsdf.inputs['Subsurface Weight'].default_value = params.subsurface

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
        ramp = nodes.new(type='ShaderNodeValToRGB')
        ramp.name = "AICSS_ColorRamp"
        ramp.location = (-300, 200)
        # Cartoonisation: build a discrete colour ramp matching colorLevels
        _populate_color_ramp(ramp, params.color_levels)

        tree.links.new(tex.outputs['Color'], ramp.inputs['Fac'])
        tree.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

    # ── Normal map (Phase 1 v1) ─────────────────────────────────────────────
    # Phase 1: we look for a sibling ``*_normal.png`` next to the diffuse
    # PNG. Phase 2 will switch to the manifest's normalMapUrl field.
    normal_path = _sibling_normal(image_path) if image_path else None
    if normal_path:
        ntex = nodes.new(type='ShaderNodeTexImage')
        ntex.name = "AICSS_NormalTex"
        ntex.location = (-600, -200)
        try:
            ntex.image = _load_image(normal_path)
        except Exception:
            ntex.image = None
        ntex.image.colorspace_settings.name = 'Non-Color'

        nmap = nodes.new(type='ShaderNodeNormalMap')
        nmap.name = "AICSS_NormalMap"
        nmap.location = (-300, -200)
        nmap.inputs['Strength'].default_value = params.normal_strength

        tree.links.new(ntex.outputs['Color'], nmap.inputs['Color'])
        tree.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])


def apply_paper_material(obj, *, image_path: Optional[str] = None,
                          roughness: float = 0.9,
                          normal_strength: float = 0.8) -> None:
    """Assign the paper material to ``obj``.

    Looks up the canonical AICSS_PaperMaterial data-block (creating it on
    first use) and assigns it to all mesh slots. ``image_path`` is
    forwarded to the diffuse texture node when provided.
    """
    if not _HAS_BPY:
        return
    material = bpy.data.materials.get(PAPER_MATERIAL_NAME)
    if material is None:
        material = bpy.data.materials.new(PAPER_MATERIAL_NAME)

    params = PaperMaterialParams(
        roughness=roughness,
        normal_strength=normal_strength,
    )
    build_paper_node_graph(material, image_path=image_path, params=params)

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


def _sibling_normal(diffuse_path: str) -> Optional[str]:
    """If ``diffuse_path`` is ``layer_foreground.png``, return
    ``layer_foreground_normal.png`` if that file exists."""
    if not diffuse_path:
        return None
    stem, ext = os.path.splitext(diffuse_path)
    normal = f"{stem}_normal{ext}"
    return normal if os.path.exists(normal) else None