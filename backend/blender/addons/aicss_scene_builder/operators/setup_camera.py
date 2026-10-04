"""
setup_camera operator — creates a Blender camera with FOV/distance tuned
for the requested shot type, and a target empty so OrbitControls (in the
Blender viewport) and downstream render scripts have something to look at.

Shot type → FOV mapping is in ``utils.scene_utils.DEFAULT_CAMERA_FOV``.
We use Blender's perspective camera with ``sensor_fit='HORIZONTAL'`` so the
FOV matches a horizontal field-of-view (the same convention Three.js uses).

T06 扩展：``AICSS_OT_setup_camera_animation`` 读 manifest 的 ``cameraPath``
关键帧序列，用 ``keyframe_insert`` 写相机位置 / 旋转 / 焦距 F-Curve。
"""
from __future__ import annotations

import math
import os

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
        # Place the camera at (0, 0, +distance) looking at the target. We
        # use Blender's default camera orientation (looks down -Z), so the
        # camera sits at positive Z and looks toward -Z (toward the target
        # at the origin). Layer planes live in the XY plane at negative Z
        # offsets (z=0 is the target/character, negative Z is farther away).
        # Camera at +Z looks toward -Z, so layers at negative Z are in front
        # of the camera. Plane normals point +Z (toward the camera).
        cam_obj.location = (0.0, 0.0, self.distance)
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


class AICSS_OT_setup_camera_animation(Operator):
    """Read manifest's ``cameraPath`` keyframes and bake them onto the
    active scene camera via ``keyframe_insert``.

    Properties:
        manifest_path: Path to the AICSS manifest.json exported by the
            backend. The manifest must contain a ``cameraPath`` field — a
            list of ``{time, position: [x,y,z], target: [x,y,z], fov}`` dicts.
        fps: Timeline frame rate (default 24). Each keyframe's ``time`` is
            a 0..1 normalised value mapped to ``frame = round(time * fps * duration)``.
            When the manifest has no ``duration`` field we assume 1 second
            per unit time, i.e. ``frame = round(time * fps)``.
        duration: Override the manifest's duration (seconds). When 0, the
            operator reads ``manifest.duration`` (fallback 5.0s).
        camera_name: Name of the camera object to animate. When the object
            doesn't exist, a new camera is created.
    """
    bl_idname = "aicss.setup_camera_animation"
    bl_label = "Set Camera Animation"
    bl_options = {'REGISTER', 'UNDO'}

    manifest_path: StringProperty(
        name="Manifest Path",
        description="Path to the AICSS manifest.json with a cameraPath field",
        subtype='FILE_PATH',
    )
    fps: FloatProperty(
        name="FPS",
        default=24.0,
        min=1.0,
        max=120.0,
        description="Timeline frame rate",
    )
    duration: FloatProperty(
        name="Duration (s)",
        default=0.0,
        min=0.0,
        description="Override manifest duration. 0 = read from manifest (fallback 5s).",
    )
    camera_name: StringProperty(
        name="Camera Name",
        default="AICSS_Camera",
    )

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        if not self.manifest_path or not os.path.exists(self.manifest_path):
            self.report({'ERROR'}, f"Manifest not found: {self.manifest_path}")
            return {'CANCELLED'}

        from ..utils.scene_utils import read_manifest

        try:
            manifest = read_manifest(self.manifest_path)
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to read manifest: {exc}")
            return {'CANCELLED'}

        camera_path = manifest.get("cameraPath")
        # 向后兼容：旧 manifest 没有 cameraPath 字段时不报错，但用 manifest.camera
        # 创建一个静态相机（render_queue 需要相机才能渲染）
        if not camera_path:
            # 用 manifest.camera 创建静态相机
            cam_info = manifest.get("camera") or {}
            shot_type = (cam_info.get("shotType") or "wide").lower()
            fov = float(cam_info.get("fov") or 0.0)
            distance = float(cam_info.get("distance") or 12.0)
            target = cam_info.get("target") or [0.0, 0.0, 0.0]
            # 借用 setup_camera operator 的逻辑
            try:
                bpy.ops.aicss.setup_camera(
                    shot_type=shot_type if shot_type in ("wide","medium","closeup","extreme_closeup") else "wide",
                    fov=fov, distance=distance,
                    target_x=float(target[0]), target_y=float(target[1]), target_z=float(target[2]),
                )
            except Exception as exc:
                self.report({'WARNING'}, f"cameraPath empty and setup_camera failed: {exc}")

            self.report(
                {'WARNING'},
                "Manifest has no cameraPath field — created static camera from manifest.camera",
            )
            return {'FINISHED'}

        # ── 找到 / 创建相机对象 ──────────────────────────────────────────────
        cam_obj = bpy.data.objects.get(self.camera_name)
        if cam_obj is None:
            cam_data = bpy.data.cameras.new(self.camera_name)
            cam_data.lens_unit = 'FOV'
            cam_data.sensor_fit = 'HORIZONTAL'
            cam_obj = bpy.data.objects.new(self.camera_name, cam_data)
            context.scene.collection.objects.link(cam_obj)
        if cam_obj.type != 'CAMERA':
            self.report({'ERROR'}, f"Object {self.camera_name} is not a camera")
            return {'CANCELLED'}
        cam_data = cam_obj.data

        # ── 时间映射 ─────────────────────────────────────────────────────────
        duration = self.duration
        if duration <= 0.0:
            duration = float(manifest.get("duration") or 5.0)
        scene = context.scene
        scene.render.fps = int(round(self.fps))
        # 清掉 Track-To 约束，否则旋转关键帧会被覆盖
        for c in list(cam_obj.constraints):
            if c.type == 'TRACK_TO':
                cam_obj.constraints.remove(c)

        # ── 写关键帧 ─────────────────────────────────────────────────────────
        # 关键帧插值：直接 set + keyframe_insert。Blender 4.x 用 data_path:
        #   location → cam_obj.location
        #   rotation → cam_obj.rotation_euler
        #   focal length → cam_data.lens (mm) — 我们把 fov(deg) 转 lens
        #     lens = sensor_width / (2 * tan(fov/2))
        #     sensor_width 默认 36mm (full-frame)
        sensor_w = cam_data.sensor_width if cam_data.sensor_width > 0 else 36.0

        inserted = 0
        cam_obj.animation_data_create()
        for kf in camera_path:
            try:
                t = float(kf.get("time", 0.0))
                pos = kf.get("position", [0.0, 0.0, 0.0])
                tgt = kf.get("target", [0.0, 0.0, 0.0])
                fov_deg = float(kf.get("fov", 35.0))
            except Exception:
                continue

            frame = int(round(t * self.fps * duration))
            if frame < 1:
                frame = 1

            # 位置
            cam_obj.location = (float(pos[0]), float(pos[1]), float(pos[2]))
            cam_obj.keyframe_insert(data_path="location", frame=frame)

            # 朝向：从 position 看向 target
            dx = float(tgt[0]) - float(pos[0])
            dy = float(tgt[1]) - float(pos[1])
            dz = float(tgt[2]) - float(pos[2])
            # Blender 相机默认朝 -Z，up +Y。用 track_quat 比较麻烦，
            # 这里直接算 euler：让 -Z 指向 (dx,dy,dz)，up 为 +Y。
            # 用 mathutils.Vector.to_track_quat 是最稳的方式。
            try:
                from mathutils import Matrix, Vector
                direction = Vector((dx, dy, dz))
                if direction.length > 1e-6:
                    # 相机朝 -Z，世界上方向锁在 +Y，只偏航不滚转。
                    forward = direction.normalized()
                    cam_z = -forward
                    cam_x = Vector((0.0, 1.0, 0.0)).cross(cam_z)
                    if cam_x.length < 1e-5:
                        cam_x = Vector((1.0, 0.0, 0.0))
                    cam_x.normalize()
                    cam_y = cam_z.cross(cam_x).normalized()
                    rot = Matrix((
                        (cam_x.x, cam_y.x, cam_z.x),
                        (cam_x.y, cam_y.y, cam_z.y),
                        (cam_x.z, cam_y.z, cam_z.z),
                    ))
                    cam_obj.rotation_euler = rot.to_euler('XYZ')
                    cam_obj.keyframe_insert(data_path="rotation_euler", frame=frame)
            except Exception:
                # mathutils 在 Blender 内一定可用；失败则跳过旋转
                pass

            # 焦距：fov(deg) → lens(mm)
            fov_rad = math.radians(max(1.0, min(fov_deg, 170.0)))
            lens = sensor_w / (2.0 * math.tan(fov_rad / 2.0))
            cam_data.lens = lens
            cam_data.keyframe_insert(data_path="lens", frame=frame)

            inserted += 1

        context.scene.camera = cam_obj
        # 设定时间线范围
        try:
            scene.frame_start = 0
            scene.frame_end = max(int(round(self.fps * duration)), 1)
        except Exception:
            pass

        self.report(
            {'INFO'},
            f"Baked {inserted} camera keyframes (fps={int(self.fps)}, dur={duration:.1f}s)",
        )
        return {'FINISHED'}