"""
aicss_panel — sidebar panel for the AICSS Scene Builder addon.

Shows up under View3D > Sidebar (N-panel) > AICSS tab when the addon is
enabled. Exposes 4 buttons that map to the 4 operators in ``operators/``:

  * "Import Scene"     → AICSS_OT_import_layers
  * "Apply Paper Material" → AICSS_OT_apply_paper_material
  * "Set Camera"       → AICSS_OT_setup_camera
  * "Add Lighting"     → AICSS_OT_add_lighting

The panel is a thin wrapper — every button just invokes its operator,
which carries its own properties (manifest path, FOV, lighting preset, …).
This keeps the panel boilerplate minimal and centralises parameter logic
in the operator classes.
"""
from __future__ import annotations

try:
    import bpy
    from bpy.types import Panel
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Panel:  # type: ignore[no-redef]
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'AICSS'


class AICSS_PT_panel(Panel):
    """Sidebar panel exposing the AICSS Scene Builder workflow."""
    bl_label = "AICSS Scene Builder"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'AICSS'

    def draw(self, context):
        if not _HAS_BPY:
            return
        layout = self.layout

        # Section 1 — Import
        box = layout.box()
        box.label(text="Import", icon='IMPORT')
        col = box.column(align=True)
        col.operator("aicss.import_layers", icon='MESH_PLANE')

        # Section 2 — Materials
        box = layout.box()
        box.label(text="Materials", icon='MATERIAL')
        col = box.column(align=True)
        col.operator("aicss.apply_paper_material", icon='MATERIAL')

        # Section 3 — Camera
        box = layout.box()
        box.label(text="Camera", icon='CAMERA_DATA')
        col = box.column(align=True)
        col.operator("aicss.setup_camera", icon='CAMERA_DATA')
        col.operator("aicss.setup_camera_animation", icon='KEYFRAME_HLT')

        # Section 4 — Lighting
        box = layout.box()
        box.label(text="Lighting", icon='LIGHT')
        col = box.column(align=True)
        col.operator("aicss.add_lighting", icon='LIGHT_SUN')

        # Section 5 — Verify
        box = layout.box()
        box.label(text="Verify", icon='RENDER_STILL')
        col = box.column(align=True)
        col.operator("aicss.verify_cycles", icon='RENDER_ANIMATION')

        # Section 6 — Animation (T08 / T09)
        box = layout.box()
        box.label(text="Animation", icon='SEQUENCE')
        col = box.column(align=True)
        col.operator("aicss.import_character_frames", icon='IMAGE_SEQ')
        col.operator("aicss.layer_motion", icon='FORCE_HARMONIC')

        # Section 7 — Render Queue (T07)
        box = layout.box()
        box.label(text="Render Queue", icon='RENDER_ANIMATION')
        col = box.column(align=True)
        col.operator("aicss.render_queue", icon='FILE_MOVIE')