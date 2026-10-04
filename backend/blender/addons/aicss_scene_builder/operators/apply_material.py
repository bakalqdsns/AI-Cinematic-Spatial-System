"""
apply_material operator — applies the AICSS paper material to the active
selection. Useful when the user wants to re-apply the paper material to
objects imported separately, or to tweak material parameters on existing
layers.

The actual node graph lives in ``materials/paper_material.py``; this
operator is a thin wrapper that calls ``apply_paper_material`` and handles
the Blender Operator protocol (execute / invoke / poll).
"""
from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, FloatProperty, BoolProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def FloatProperty(**kw): return None  # type: ignore[no-redef]
    def BoolProperty(**kw): return None  # type: ignore[no-redef]


class AICSS_OT_apply_paper_material(Operator):
    """Apply the AICSS paper material to selected mesh objects.

    Properties:
        image_path: Optional path to a PNG that becomes the diffuse texture.
            When empty, the material has no diffuse map (white base).
        roughness: 0.5–1.0, default 0.9 (matches paper visual roughness).
        normal_strength: 0.0–1.0, default 0.8 (Phase 2: pulled from the
            manifest's normalMapUrl).
        subsurface: 0.0–1.0, default 0.15 (T12 — SSS 透纸感).
        use_fibre: bool, default False (T12 — 纤维法线噪声叠加).
    """
    bl_idname = "aicss.apply_paper_material"
    bl_label = "Apply Paper Material"
    bl_options = {'REGISTER', 'UNDO'}

    image_path: StringProperty(
        name="Image Path",
        subtype='FILE_PATH',
    )
    roughness: FloatProperty(
        name="Roughness",
        default=0.9,
        min=0.5,
        max=1.0,
    )
    normal_strength: FloatProperty(
        name="Normal Strength",
        default=0.8,
        min=0.0,
        max=1.0,
    )
    subsurface: FloatProperty(
        name="Subsurface (SSS)",
        default=0.15,
        min=0.0,
        max=1.0,
        description="Subsurface scattering weight — 逆光边缘透纸感",
    )
    use_fibre: BoolProperty(
        name="Paper Fibre",
        default=False,
        description="叠加细密噪声到法线，模拟纸纤维质感",
    )

    @classmethod
    def poll(cls, context):
        if not _HAS_BPY:
            return False
        return context.mode == 'OBJECT' and context.selected_objects

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        from ..materials.paper_material import apply_paper_material

        applied = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            apply_paper_material(
                obj,
                image_path=self.image_path or obj.get("aicss_layer_png"),
                roughness=self.roughness,
                normal_strength=self.normal_strength,
                subsurface=self.subsurface,
                use_fibre=self.use_fibre,
            )
            applied += 1

        if applied == 0:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Applied paper material to {applied} object(s)")
        return {'FINISHED'}