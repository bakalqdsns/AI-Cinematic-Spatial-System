"""
add_lighting operator — creates a 3-point lighting rig (Key + Fill + Rim)
based on a JSON preset or the manifest's ``lighting`` block.

Each light is a Blender lamp object (SUN / AREA / SPOT) whose energy,
colour, and orientation match the preset. We also add an ``Empty`` at the
scene origin so future shaders / render scripts can locate the rig.
"""
from __future__ import annotations

import json
import os

try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, EnumProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def EnumProperty(**kw): return None  # type: ignore[no-redef]


# Built-in preset table (Phase 1 v1). Future versions may load these from
# the manifest's lighting block or from disk.
BUILTIN_PRESETS = {
    "warm_interior": {
        "key":  {"type": "SUN",  "energy": 3.0, "color": [1.0, 0.96, 0.88],
                 "location": [8.0, -8.0, 12.0], "rotation": [0.6, 0.0, 0.5]},
        "fill": {"type": "AREA", "energy": 1.5, "color": [0.8, 0.9, 1.0],   "size": 5.0,
                 "location": [-8.0, -6.0, 8.0], "rotation": [0.7, 0.0, -0.5]},
        "rim":  {"type": "SPOT", "energy": 2.0, "color": [1.0, 0.93, 0.8],
                 "location": [0.0, 8.0, 10.0], "rotation": [-0.7, 0.0, 0.0]},
    },
    "cool_exterior": {
        "key":  {"type": "SUN",  "energy": 4.0, "color": [1.0, 1.0, 1.0],
                 "location": [8.0, -8.0, 12.0], "rotation": [0.5, 0.0, 0.4]},
        "fill": {"type": "AREA", "energy": 1.0, "color": [0.6, 0.8, 1.0],   "size": 6.0,
                 "location": [-8.0, -6.0, 8.0], "rotation": [0.6, 0.0, -0.4]},
        "rim":  {"type": "SPOT", "energy": 1.5, "color": [0.9, 0.95, 1.0],
                 "location": [0.0, 8.0, 10.0], "rotation": [-0.7, 0.0, 0.0]},
    },
    "dramatic": {
        "key":  {"type": "SPOT", "energy": 6.0, "color": [1.0, 0.85, 0.7],
                 "location": [6.0, -6.0, 10.0], "rotation": [0.7, 0.0, 0.6]},
        "fill": {"type": "AREA", "energy": 0.4, "color": [0.4, 0.5, 0.7],   "size": 8.0,
                 "location": [-7.0, -5.0, 6.0], "rotation": [0.7, 0.0, -0.5]},
        "rim":  {"type": "SPOT", "energy": 3.0, "color": [1.0, 0.9, 0.6],
                 "location": [0.0, 8.0, 9.0], "rotation": [-0.7, 0.0, 0.0]},
    },
    # T14 — 新增 3 套预设
    "tense_night": {
        "key":  {"type": "SPOT", "energy": 2.5, "color": [0.55, 0.65, 1.0],
                 "location": [6.0, -6.0, 9.0], "rotation": [0.6, 0.0, 0.5]},
        "fill": {"type": "AREA", "energy": 0.3, "color": [0.3, 0.35, 0.5], "size": 7.0,
                 "location": [-7.0, -5.0, 5.0], "rotation": [0.7, 0.0, -0.5]},
        "rim":  {"type": "SPOT", "energy": 4.0, "color": [1.0, 0.7, 0.4],
                 "location": [0.0, 7.0, 8.0], "rotation": [-0.7, 0.0, 0.0]},
    },
    "soft_morning": {
        "key":  {"type": "SUN",  "energy": 2.5, "color": [1.0, 0.92, 0.78],
                 "location": [10.0, -10.0, 6.0], "rotation": [1.0, 0.0, 0.7]},
        "fill": {"type": "AREA", "energy": 2.0, "color": [0.95, 0.97, 1.0], "size": 9.0,
                 "location": [-9.0, -7.0, 6.0], "rotation": [0.9, 0.0, -0.6]},
        "rim":  {"type": "SPOT", "energy": 1.2, "color": [1.0, 0.95, 0.85],
                 "location": [0.0, 8.0, 7.0], "rotation": [-0.8, 0.0, 0.0]},
    },
    "misty_grey": {
        "key":  {"type": "AREA", "energy": 2.0, "color": [0.85, 0.87, 0.9], "size": 8.0,
                 "location": [4.0, -8.0, 10.0], "rotation": [0.5, 0.0, 0.3]},
        "fill": {"type": "AREA", "energy": 2.0, "color": [0.8, 0.83, 0.88], "size": 10.0,
                 "location": [-6.0, -6.0, 8.0], "rotation": [0.6, 0.0, -0.4]},
        "rim":  {"type": "AREA", "energy": 1.0, "color": [0.75, 0.78, 0.82], "size": 6.0,
                 "location": [0.0, 6.0, 6.0], "rotation": [-0.6, 0.0, 0.0]},
    },
}


class AICSS_OT_add_lighting(Operator):
    """Add a 3-point lighting rig to the active scene.

    Properties:
        preset: warm_interior | cool_exterior | dramatic | custom
        preset_path: Path to a custom JSON preset (only used when preset='custom').
    """
    bl_idname = "aicss.add_lighting"
    bl_label = "Add AICSS Lighting"
    bl_options = {'REGISTER', 'UNDO'}

    preset: EnumProperty(
        name="Preset",
        items=[
            ("warm_interior", "Warm Interior", "Cozy indoor — soft yellow key"),
            ("cool_exterior", "Cool Exterior", "Daylight outdoor — neutral key"),
            ("dramatic", "Dramatic", "Theatrical — high contrast"),
            ("custom", "Custom JSON…", "Load a custom preset from disk"),
        ],
        default="warm_interior",
    )
    preset_path: StringProperty(
        name="Preset Path",
        subtype='FILE_PATH',
    )

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        if self.preset == "custom":
            if not self.preset_path or not os.path.exists(self.preset_path):
                self.report({'ERROR'}, f"Preset not found: {self.preset_path}")
                return {'CANCELLED'}
            with open(self.preset_path, "r", encoding="utf-8") as fp:
                rig = json.load(fp)
        else:
            rig = BUILTIN_PRESETS.get(self.preset, BUILTIN_PRESETS["warm_interior"])

        # Create a rig empty for grouping + tracking
        rig_name = f"AICSS_LightingRig_{self.preset}"
        rig_empty = bpy.data.objects.get(rig_name)
        if rig_empty is None:
            bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
            rig_empty = bpy.context.active_object
            rig_empty.name = rig_name
            rig_empty["aicss_role"] = "lighting_rig"

        added = 0
        for role, spec in rig.items():
            obj = _create_light(role, spec)
            if obj is None:
                continue
            obj.parent = rig_empty
            added += 1

        self.report({'INFO'}, f"Added {added} lights (preset={self.preset})")
        return {'FINISHED'}


def _create_light(role, spec):
    """Create a single light object from a preset dict.

    Returns the created object or None on failure.
    """
    light_type = spec.get("type", "SUN").upper()
    if light_type not in ("SUN", "AREA", "SPOT", "POINT"):
        return None

    light_data = bpy.data.lights.new(name=f"AICSS_{role}", type=light_type)
    light_data.energy = float(spec.get("energy", 1.0))
    color = spec.get("color", [1.0, 1.0, 1.0])
    light_data.color = (float(color[0]), float(color[1]), float(color[2]))
    if "size" in spec:
        light_data.size = float(spec["size"])

    light_obj = bpy.data.objects.new(f"AICSS_{role}_{light_type}", light_data)
    bpy.context.scene.collection.objects.link(light_obj)

    # T14 — 优先用 spec 里的 location/rotation；否则按 role 给默认位置。
    loc = spec.get("location")
    if isinstance(loc, (list, tuple)) and len(loc) >= 3:
        light_obj.location = (float(loc[0]), float(loc[1]), float(loc[2]))
    else:
        if role == "key":
            light_obj.location = (8.0, -8.0, 12.0)
        elif role == "fill":
            light_obj.location = (-8.0, -6.0, 8.0)
        elif role == "rim":
            light_obj.location = (0.0, 8.0, 10.0)

    rot = spec.get("rotation")
    if isinstance(rot, (list, tuple)) and len(rot) >= 3:
        light_obj.rotation_euler = (float(rot[0]), float(rot[1]), float(rot[2]))

    light_obj["aicss_role"] = f"light_{role}"
    return light_obj