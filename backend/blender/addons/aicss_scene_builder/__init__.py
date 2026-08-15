"""
AICSS Scene Builder — Blender Addon (Phase 1.2)

Loads the 4 RGBA layer PNGs exported by the AICSS backend's
``POST /api/aicss/layers/export`` endpoint and assembles them into a
paper-diorama scene:

  * One mesh plane per depth layer (foreground / midground / background / sky)
  * Each plane positioned along the Z-axis at the canonical offset
    (sky=-20, background=-12, midground=-6, foreground=-2)
  * Paper material applied via ``materials/paper_material.py``
  * Camera + 3-point lighting set up via the operators in ``operators/``

Install:
  1. Open Blender → Edit → Preferences → Add-ons → Install…
  2. Pick ``backend/blender/addons/aicss_scene_builder.zip`` (or this folder).
  3. Enable "AICSS Scene Builder".
  4. The "AICSS" panel appears in the 3D viewport's sidebar (N-panel).

Manifest format:
  The plugin reads a ``manifest.json`` exported by the backend. The minimal
  schema is::

      {
        "shotId": "shot_001",
        "sceneId": "scene_forest",
        "width": 1920,
        "height": 1080,
        "layers": {
          "foreground":  "/abs/path/to/layer_foreground.png",
          "midground":   "/abs/path/to/layer_midground.png",
          "background":  "/abs/path/to/layer_background.png",
          "sky":         "/abs/path/to/layer_sky.png"
        },
        "zOffsets": [
          {"layer": "sky",        "zOffset": -20.0, "zMin": 50.0, "zMax": 9999.0},
          {"layer": "background", "zOffset": -12.0, "zMin": 15.0, "zMax": 50.0},
          {"layer": "midground",  "zOffset": -6.0,  "zMin": 5.0,  "zMax": 15.0},
          {"layer": "foreground", "zOffset": -2.0,  "zMin": 0.0,  "zMax": 5.0}
        ],
        "camera": {
          "shotType": "wide",     # wide | medium | closeup
          "fov": 35.0,
          "distance": 12.0,
          "target": [0.0, 0.0, 0.0]
        },
        "lighting": {
          "key":   {"type": "SUN",   "energy": 3.0, "color": [1.0, 0.96, 0.88]},
          "fill":  {"type": "AREA",  "energy": 1.5, "color": [0.8, 0.9, 1.0],   "size": 5.0},
          "rim":   {"type": "SPOT",  "energy": 2.0, "color": [1.0, 0.93, 0.8]}
        }
      }

The plugin doesn't depend on Blender being installed to *parse* this
module — operators are guarded with ``import bpy`` and gracefully no-op
when running outside Blender (useful for unit-testing the manifest
reader in CI).
"""

bl_info = {
    "name": "AICSS Scene Builder",
    "author": "AICSS Team",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > AICSS",
    "description": "Import AICSS scene manifests and assemble paper-diorama scenes.",
    "category": "Import-Export",
}

# Module re-exports for unit-testing outside Blender
from .utils.scene_utils import (
    Z_OFFSETS,
    LAYER_ORDER,
    read_manifest,
    normalize_manifest,
)

__all__ = (
    "bl_info",
    "Z_OFFSETS",
    "LAYER_ORDER",
    "read_manifest",
    "normalize_manifest",
)


def register():
    """Register Blender classes — only called inside Blender.

    Imports are deferred to avoid failing in non-Blender environments
    (CI, unit tests).
    """
    try:
        import bpy
    except ImportError:
        # Running outside Blender — nothing to register.
        return

    from .operators import import_layers, setup_camera, add_lighting, apply_material
    from .ui.aicss_panel import AICSS_PT_panel

    for cls in (
        import_layers.AICSS_OT_import_layers,
        setup_camera.AICSS_OT_setup_camera,
        add_lighting.AICSS_OT_add_lighting,
        apply_material.AICSS_OT_apply_paper_material,
        AICSS_PT_panel,
    ):
        bpy.utils.register_class(cls)


def unregister():
    """Unregister Blender classes — mirror of ``register``."""
    try:
        import bpy
    except ImportError:
        return

    from .operators import import_layers, setup_camera, add_lighting, apply_material
    from .ui.aicss_panel import AICSS_PT_panel

    for cls in (
        AICSS_PT_panel,
        apply_material.AICSS_OT_apply_paper_material,
        add_lighting.AICSS_OT_add_lighting,
        setup_camera.AICSS_OT_setup_camera,
        import_layers.AICSS_OT_import_layers,
    ):
        bpy.utils.unregister_class(cls)