"""
setup_camera operator — creates a Blender camera with FOV/distance tuned
for the requested shot type, and a target empty so OrbitControls (in the
Blender viewport) and downstream render scripts have something to look at.

Shot type → FOV mapping is in ``utils.scene_utils.DEFAULT_CAMERA_FOV``.
We use Blender's perspective camera with ``sensor_fit='HORIZONTAL'`` so the
FOV matches a horizontal field-of-view (the same convention Three.js uses).
"""
from __future__ import annotations

try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, FloatProperty, EnumProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def FloatProperty(**kw): return None  # type: ignore[no-redef]
    def EnumProperty(**kw): return None  # type: ignore[no-redef]


class AICSS_OT_setup_camera(Operator):
    """Create a Blender camera positioned for the AICSS scene.

    Properties:
        shot_type: wide | medium | closeup | extreme_closeup
        fov: Override FOV (degrees). When 0, uses ``DEFAULT_CAMERA_FOV[shot_type]``.
        distance: Camera distance from target (Blender units).
        target_x/y/z: World-space coordinates of the camera target (an Empty
            is added at this location so other tools can hook to it).
    """
    bl_idname = "aicss.setup_camera"
    bl_label = "Setup AICSS Camera"
    bl_options = {'REGISTER', 'UNDO'}

    shot_type: EnumProperty(
        name="Shot Type",
        items=[
            ("wide", "Wide", "Wide establishing shot"),
            ("medium", "Medium", "Medium framing"),
            ("closeup", "Closeup", "Close-up"),
            ("extreme_closeup", "Extreme Closeup", "Extreme close-up"),
        ],
        default="wide",
    )
    fov: FloatProperty(
        name="FOV (deg)",
        default=0.0,
        min=0.0,
        max=180.0,
        description="Override FOV. Leave at 0 to use the shot-type default.",
    )
    distance: FloatProperty(
        name="Distance",
        default=12.0,
        min=0.1,
        max=200.0,
    )
    target_x: FloatProperty(name="Target X", default=0.0)
    target_y: FloatProperty(name="Target Y", default=0.0)
    target_z: FloatProperty(name="Target Z", default=0.0)

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        from ..utils.scene_utils import DEFAULT_CAMERA_FOV

        if self.fov > 0.0:
            fov = self.fov
        else:
            fov = DEFAULT_CAMERA_FOV.get(self.shot_type, DEFAULT_CAMERA_FOV["wide"])

        # Create or reuse the target empty
        target_name = "AICSS_CameraTarget"
        target = bpy.data.objects.get(target_name)
        if target is None:
            bpy.ops.object.empty_add(
                type='PLAIN_AXES',
                location=(self.target_x, self.target_y, self.target_z),
            )
            target = bpy.context.active_object
            target.name = target_name
            target["aicss_role"] = "camera_target"
        else:
            target.location = (self.target_x, self.target_y, self.target_z)

        # Create or reuse the camera
        cam_name = "AICSS_Camera"
        cam_data = bpy.data.cameras.get(cam_name)
        if cam_data is None:
            cam_data = bpy.data.cameras.new(cam_name)
        cam_data.lens_unit = 'FOV'
        cam_data.sensor_fit = 'HORIZONTAL'
        cam_data.angle = fov * (3.141592653589793 / 180.0)  # degrees → radians

        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj is None:
            cam_obj = bpy.data.objects.new(cam_name, cam_data)
            context.scene.collection.objects.link(cam_obj)
        # Place the camera at (0, 0, distance) looking at the target. We
        # use a fixed offset (negative Y) so the camera faces the scene
        # along the +Y axis — Blender's default.
        cam_obj.location = (0.0, -self.distance, 0.0)
        cam_obj["aicss_role"] = "camera"
        cam_obj["aicss_shot_type"] = self.shot_type
        cam_obj["aicss_fov"] = fov

        # Track-to constraint so the camera always looks at the target
        constraint = cam_obj.constraints.get('TrackToTarget')
        if constraint is None:
            constraint = cam_obj.constraints.new(type='TRACK_TO')
            constraint.name = 'TrackToTarget'
        constraint.target = target
        constraint.track_axis = 'TRACK_NEGATIVE_Z'
        constraint.up_axis = 'UP_Y'

        # Make the new camera the active scene camera
        context.scene.camera = cam_obj

        self.report({'INFO'}, f"Camera set: shot={self.shot_type}, fov={fov:.1f}°, dist={self.distance:.1f}")
        return {'FINISHED'}