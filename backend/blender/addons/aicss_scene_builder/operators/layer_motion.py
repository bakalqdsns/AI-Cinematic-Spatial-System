"""
layer_motion operator (T09) — 给场景的深度层平面加位置 F-Curve，
按视差规律移动（前景偏移大、背景偏移小），模拟纸片剧场晃动 / 视差。

读 manifest 的 ``layerMotion`` 字段（每层偏移曲线）：
    "layerMotion": [
        {"layer": "foreground", "keyframes": [
            {"time": 0.0, "offsetX": 0.0, "offsetY": 0.0},
            {"time": 0.5, "offsetX": 0.3, "offsetY": -0.1},
            {"time": 1.0, "offsetX": 0.0, "offsetY": 0.0}
        ]},
        ...
    ]

如果 manifest 没有 ``layerMotion``，从 ``cameraPath`` 推导视差：按深度
差速（前景偏移大、背景偏移小）。``parallaxIntensity`` operator 属性控制
晃动幅度。

非 Blender 环境下 operator 类仍可 import，但 register 为 no-op。
"""
from __future__ import annotations

import math
import os

try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, FloatProperty, IntProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def FloatProperty(**kw): return None  # type: ignore[no-redef]
    def IntProperty(**kw): return None  # type: ignore[no-redef]


# 与 utils.scene_utils.Z_OFFSETS 一致
_Z_OFFSETS = {
    "sky": -20.0,
    "background": -12.0,
    "midground": -6.0,
    "foreground": -2.0,
    "ground": -1.5,
}


def _parallax_factor(layer_z: float) -> float:
    """前景 → 1.0，天空 → 0.0 的归一化因子。

    foreground (z=-2) → 1.0，sky (z=-20) → 0.0，中间线性插值。
    """
    fg_z = _Z_OFFSETS["foreground"]
    sky_z = _Z_OFFSETS["sky"]
    if fg_z == sky_z:
        return 0.0
    f = (layer_z - sky_z) / (fg_z - sky_z)
    return max(0.0, min(1.0, f))


def _find_layer_plane(layer: str, shot_id: str):
    """按 aicss_layer 属性找层平面。找不到返回 None。"""
    target_name = f"AICSS_Layer_{layer}"
    for obj in bpy.data.objects:
        if obj.get("aicss_layer") == layer:
            return obj
        if obj.name == target_name:
            return obj
    return None


def _apply_layer_motion_keyframes(obj, keyframes, fps: int, duration: float,
                                 base_x: float, base_y: float, base_z: float,
                                 intensity: float) -> int:
    """给 obj 的 location 写 F-Curve。返回插入的关键帧数。"""
    inserted = 0
    obj.animation_data_create()
    # 清掉旧 animation_data 以避免叠加
    try:
        if obj.animation_data.action:
            obj.animation_data.action = None
    except Exception:
        pass

    for kf in keyframes:
        try:
            t = float(kf.get("time", 0.0))
            ox = float(kf.get("offsetX", 0.0)) * intensity
            oy = float(kf.get("offsetY", 0.0)) * intensity
        except Exception:
            continue
        frame = int(round(t * fps * duration)) if duration > 0 else int(round(t * fps))
        obj.location = (base_x + ox, base_y + oy, base_z)
        obj.keyframe_insert(data_path="location", frame=frame)
        inserted += 1
    return inserted


def _derive_layer_motion_from_camera_path(camera_path, manifest, intensity: float):
    """从 cameraPath 推导每层的视差偏移曲线。

    返回 ``{layer: [keyframes]}``，每个 keyframe 是 ``{time, offsetX, offsetY}``。
    视差方向：相机右移 → 层平面左移（反向），位移 ∝ parallax_factor * intensity。
    """
    if not camera_path:
        return {}

    # 用第一帧作为基准位置
    try:
        base_pos = camera_path[0].get("position", [0.0, 0.0, 0.0])
        base_x = float(base_pos[0])
        base_y = float(base_pos[1])
    except Exception:
        base_x = base_y = 0.0

    out: dict = {}
    for layer, z in _Z_OFFSETS.items():
        factor = _parallax_factor(z)
        kfs = []
        for kf in camera_path:
            try:
                t = float(kf.get("time", 0.0))
                pos = kf.get("position", [0.0, 0.0, 0.0])
                dx = float(pos[0]) - base_x
                dy = float(pos[1]) - base_y
            except Exception:
                continue
            # 反向位移（相机右移 → 层左移），乘视差因子
            ox = -dx * factor * intensity
            oy = -dy * factor * intensity
            kfs.append({"time": t, "offsetX": ox, "offsetY": oy})
        if kfs:
            out[layer] = kfs
    return out


class AICSS_OT_layer_motion(Operator):
    """Apply parallax motion to depth-layer planes.

    Properties:
        manifest_path: Path to the AICSS manifest.json.
        parallax_intensity: Motion amplitude multiplier (default 1.0).
            Larger = more pronounced parallax. 0 = no motion.
        fps: Timeline frame rate (default 24). Each keyframe's ``time`` is
            a 0..1 normalised value mapped to ``frame = round(time * fps * duration)``.
        duration: Override the manifest's duration (seconds). 0 = read from
            manifest (fallback 5.0s).
    """
    bl_idname = "aicss.layer_motion"
    bl_label = "Apply Layer Motion"
    bl_options = {'REGISTER', 'UNDO'}

    manifest_path: StringProperty(
        name="Manifest Path",
        description="Path to the AICSS manifest.json",
        subtype='FILE_PATH',
    )
    parallax_intensity: FloatProperty(
        name="Parallax Intensity",
        default=1.0,
        min=0.0,
        max=10.0,
        description="Motion amplitude multiplier (0 = no motion)",
    )
    fps: FloatProperty(
        name="FPS",
        default=24.0,
        min=1.0,
        max=120.0,
    )
    duration: FloatProperty(
        name="Duration (s)",
        default=0.0,
        min=0.0,
        description="Override manifest duration. 0 = read from manifest (fallback 5s).",
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

        duration = self.duration
        if duration <= 0.0:
            duration = float(manifest.get("duration") or 5.0)

        # 1) 优先用 manifest.layerMotion
        layer_motion = manifest.get("layerMotion") or []
        motion_map: dict = {}
        if layer_motion:
            for entry in layer_motion:
                try:
                    layer = str(entry.get("layer", ""))
                    kfs = entry.get("keyframes") or []
                except Exception:
                    continue
                if layer and kfs:
                    motion_map[layer] = kfs
        else:
            # 2) 向后兼容：从 cameraPath 推导视差
            camera_path = manifest.get("cameraPath") or []
            if not camera_path:
                self.report(
                    {'WARNING'},
                    "Manifest has no layerMotion and no cameraPath — nothing to animate",
                )
                return {'CANCELLED'}
            motion_map = _derive_layer_motion_from_camera_path(
                camera_path, manifest, self.parallax_intensity,
            )
            if not motion_map:
                self.report({'WARNING'}, "Could not derive layer motion from cameraPath")
                return {'CANCELLED'}

        total_inserted = 0
        applied_layers = 0
        for layer, kfs in motion_map.items():
            obj = _find_layer_plane(layer, manifest.get("shotId", ""))
            if obj is None:
                self.report({'WARNING'}, f"Layer plane not found: {layer}")
                continue
            # 基准位置：当前 plane 的 location（取 z 作为深度）
            base_x = float(obj.location.x)
            base_y = float(obj.location.y)
            base_z = float(obj.location.z)
            n = _apply_layer_motion_keyframes(
                obj, kfs, int(self.fps), duration,
                base_x, base_y, base_z,
                self.parallax_intensity,
            )
            total_inserted += n
            applied_layers += 1

        self.report(
            {'INFO'},
            f"Applied motion to {applied_layers} layer(s), {total_inserted} keyframes",
        )
        return {'FINISHED'}
