"""
import_character_frames operator (T08) — 把角色的 PNG 帧序列作为
Image Sequence 贴到角色平面上，让 Blender 时间线播放时按帧切换纹理。

读 manifest 的 ``characters[]``（字段：``id`` / ``name`` / ``framesDir`` /
``frameCount`` / ``fps``，由 T11 已加）。每个角色一个平面 mesh +
``ShaderNodeTexImage`` 节点，``image_user.frame_duration`` / ``frame_start`` /
``frame_offset`` 配好帧范围，``use_auto_refresh=True`` 让 Blender 播放时
自动切换纹理帧。

角色平面位置从 manifest 的 ``position`` 读（T10 已加角色落位，这里只
补帧动画纹理 —— 如果平面已存在则复用，不存在则新建）。

第 6 轮：多帧角色附带行走轨迹——按 manifest 的 ``walkFromX`` /
``walkToX``（默认 -3 → +3）给平面 X 位置 K 两个线性关键帧，
帧序列播放时人物从画面左走到右。

非 Blender 环境下 operator 类仍可 import，但 register 为 no-op。
"""
from __future__ import annotations

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


def _list_frames(frames_dir: str) -> list:
    """返回 framesDir 下按文件名排序的 png 绝对路径。

    接受 ``seg_`` 与 ``frame_`` 前缀。两种都在时只用抠像 ``seg_``。
    都没有时退回目录里其余 png（透明仍靠图像 Alpha，不在这里做色键）。
    """
    if not frames_dir or not os.path.isdir(frames_dir):
        return []
    try:
        names = sorted(
            f for f in os.listdir(frames_dir)
            if f.lower().endswith(".png")
        )
    except Exception:
        return []
    seg_named = [f for f in names if f.lower().startswith("seg_")]
    if seg_named:
        chosen = seg_named
    else:
        frame_named = [f for f in names if f.lower().startswith("frame_")]
        chosen = frame_named or names
    return [os.path.join(frames_dir, f) for f in chosen]


def _load_image_sequence(first_frame: str):
    """加载第一帧并把 image.source 设成 SEQUENCE，让 Blender 自动识别
    后续编号帧。返回 image 数据块或 None。"""
    try:
        # check_existing=False 避免 cache 命中同名单帧
        img = bpy.data.images.load(first_frame, check_existing=False)
    except Exception:
        return None
    try:
        img.source = 'SEQUENCE'
    except Exception:
        pass
    return img


def _apply_image_sequence_material(obj, img, frame_count: int, fps: int) -> bool:
    """给 obj 套一个材质，里面是 Principled BSDF + Image Sequence 节点。
    返回 True/False 表示是否成功。"""
    try:
        # 清掉 import_layers 之前给 character plane 加的静态 paper material，
        # 否则它会留在 slot 0 覆盖动画 material（渲染用第一个 slot）。
        obj.data.materials.clear()
        mat = bpy.data.materials.new(name=obj.name + "_ImgSeq_Mat")
        obj.data.materials.append(mat)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (400, 0)
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (100, 0)
        principled.inputs["Roughness"].default_value = 0.9
        if "Specular IOR Level" in principled.inputs:
            principled.inputs["Specular IOR Level"].default_value = 0.0

        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-300, 0)
        tex.image = img
        # 关键：image_user 配帧范围 + 自动刷新
        iu = tex.image_user
        iu.frame_duration = max(1, int(frame_count))
        iu.frame_start = 1  # 时间线帧 1 对应序列帧 0（1-indexed，避开 frame 0 加载 bug）
        iu.frame_offset = 0
        iu.use_auto_refresh = True
        iu.use_cyclic = True  # 循环播放：24 帧序列覆盖整个时间线（5s@24fps=120 帧）

        links.new(tex.outputs["Color"], principled.inputs["Base Color"])
        if "Alpha" in tex.outputs:
            # RGBA 透明
            links.new(tex.outputs["Alpha"], principled.inputs["Alpha"])
            try:
                mat.blend_method = 'HASHED'
            except Exception:
                pass

        links.new(principled.outputs["BSDF"], output.inputs["Surface"])
        return True
    except Exception:
        return False


# 行走位移默认值（世界 X，米）：清单没写 walkFromX/walkToX 时，
# 多帧角色从画面左 (-3) 线性走到右 (+3)。与后端
# shot_archiver._CHARACTER_WALK_FROM_X / _CHARACTER_WALK_TO_X 一致。
DEFAULT_WALK_FROM_X = -3.0
DEFAULT_WALK_TO_X = 3.0


def _walk_range(ch):
    """读角色的行走区间。返回 (from_x, to_x)；起止相同（不走路）时返回 None。

    清单缺字段或值非法时回退到默认 -3 → +3。
    """
    try:
        from_x = float(ch.get("walkFromX", DEFAULT_WALK_FROM_X))
    except (TypeError, ValueError):
        from_x = DEFAULT_WALK_FROM_X
    try:
        to_x = float(ch.get("walkToX", DEFAULT_WALK_TO_X))
    except (TypeError, ValueError):
        to_x = DEFAULT_WALK_TO_X
    if from_x == to_x:
        return None
    return (from_x, to_x)


def _add_walk_animation(obj, ch, frame_count: int) -> bool:
    """给角色平面 K 两个 X 位置关键帧：帧 1 在 walkFromX、末帧在 walkToX，
    线性插值——帧序列播放时人物从画面左走到右，行走读得出来。
    Y/Z 不动（深度由落位决定）。单帧角色不走路。返回是否成功。"""
    if not _HAS_BPY or obj is None or int(frame_count) <= 1:
        return False
    walk = _walk_range(ch)
    if walk is None:
        return False
    from_x, to_x = walk
    end_frame = max(2, int(frame_count))
    try:
        obj.location.x = from_x
        obj.keyframe_insert(data_path="location", index=0, frame=1)
        obj.location.x = to_x
        obj.keyframe_insert(data_path="location", index=0, frame=end_frame)
        # 回到起始姿势，别让当前时间线停在终点
        obj.location.x = from_x
        obj["aicss_walk_from_x"] = from_x
        obj["aicss_walk_to_x"] = to_x
        action = getattr(obj.animation_data, "action", None) if obj.animation_data else None
        fcurves = getattr(action, "fcurves", None)
        if fcurves:
            # 严格平行画面：只保留 X（array_index=0）位移曲线，
            # 删掉任何残留的 Y/Z location 关键帧（比如 operator 重跑前
            # 旧动作留下的），保证平面不在深度/高度上漂移。
            for fc in list(fcurves):
                if fc.data_path == "location" and fc.array_index in (1, 2):
                    fcurves.remove(fc)
            for fc in fcurves:
                if fc.data_path != "location":
                    continue
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
        return True
    except Exception:
        return False


def _find_character_plane(char_id: str, shot_id: str):
    """在当前场景里按 aicss_character_id 找已落位的角色平面。
    找不到返回 None。"""
    for obj in bpy.data.objects:
        if obj.get("aicss_role") != "character":
            continue
        if obj.get("aicss_character_id") == char_id:
            return obj
        # 退而求其次：按对象名匹配
        if obj.name == f"AICSS_Character_{char_id}":
            return obj
    return None


def _create_character_plane(char, manifest):
    """新建一个角色平面（T10 已有逻辑，这里复刻一份精简版用于 T08
    单独跑的场景）。返回 obj 或 None。"""
    from .import_layers import (
        DEFAULT_CHARACTER_FILL,
        DEFAULT_CHARACTER_HEIGHT_M,
        default_character_z,
    )

    char_id = char.get("id") or char.get("name") or "character"
    position = char.get("position")
    if not position or len(position) < 3:
        # 与 import_layers / 后端一致：ground 与 foreground 之间靠前景
        # 0.35 处，人物够大又不悬空
        position = [0.0, 0.0, default_character_z(manifest)]
    scale = char.get("scale")
    if not scale or len(scale) < 2:
        s = DEFAULT_CHARACTER_HEIGHT_M / DEFAULT_CHARACTER_FILL
        scale = [round(s, 3), round(s, 3)]

    try:
        bpy.ops.mesh.primitive_plane_add(
            size=1.0,
            location=(float(position[0]), float(position[1]), float(position[2])),
        )
        obj = bpy.context.active_object
        obj.name = f"AICSS_Character_{char_id}"
        obj.scale = (float(scale[0]), float(scale[1]), 1.0)
        obj["aicss_role"] = "character"
        obj["aicss_character_id"] = str(char_id)
        obj["aicss_character_name"] = str(char.get("name", char_id))
        obj["aicss_frames_dir"] = str(char.get("framesDir", ""))
        obj["aicss_frame_count"] = int(char.get("frameCount", 0) or 0)
        obj["aicss_fps"] = int(char.get("fps", 24) or 24)
        obj["aicss_shot_id"] = manifest.get("shotId", "")
        return obj
    except Exception:
        return None


class AICSS_OT_import_character_frames(Operator):
    """Read manifest's ``characters[]`` and attach PNG frame sequences to
    character planes as Image Sequence textures.

    Properties:
        manifest_path: Path to the AICSS manifest.json. Must contain a
            ``characters`` array (T11). Each entry: ``{id, name, framesDir,
            frameCount, fps, position?, scale?, walkFromX?, walkToX?}``.
        fps: Override the manifest's per-character fps (default 0 = read
            from manifest, fallback 24).
        default_scale: Plane scale used when manifest has no ``scale`` field
            (default ≈1.78 BU — 按 1.6m 人物占帧九成估算，人物站在地面层旁)。
    """
    bl_idname = "aicss.import_character_frames"
    bl_label = "Import Character Frames"
    bl_options = {'REGISTER', 'UNDO'}

    manifest_path: StringProperty(
        name="Manifest Path",
        description="Path to the AICSS manifest.json with a characters field",
        subtype='FILE_PATH',
    )
    fps: IntProperty(
        name="FPS",
        default=0,
        min=0,
        max=120,
        description="Override manifest fps. 0 = read from manifest (fallback 24).",
    )
    default_scale_xy: FloatProperty(
        name="Default Plane Scale",
        default=1.78,
        min=0.1,
        max=50.0,
        description="Plane scale used when manifest has no `scale` field (1.6m character)",
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

        characters = manifest.get("characters") or []
        if not characters:
            self.report({'WARNING'}, "Manifest has no characters[] — nothing to import")
            return {'CANCELLED'}

        scene = context.scene
        # 时间线范围按角色帧数 / fps 推导
        max_frames = 0
        used_fps = 24

        placed = 0
        for ch in characters:
            char_id = str(ch.get("id") or ch.get("name") or "character")
            frames_dir = str(ch.get("framesDir", ""))
            frame_count = int(ch.get("frameCount", 0) or 0)
            ch_fps = int(self.fps) if self.fps > 0 else int(ch.get("fps", 24) or 24)

            frames = _list_frames(frames_dir)
            if not frames:
                self.report(
                    {'WARNING'},
                    f"Character {char_id}: no PNG frames in {frames_dir}",
                )
                continue
            if frame_count <= 0:
                frame_count = len(frames)

            # 找已落位的平面（T10 已建），找不到就新建
            obj = _find_character_plane(char_id, manifest.get("shotId", ""))
            if obj is None:
                obj = _create_character_plane(ch, manifest)
                if obj is None:
                    self.report({'WARNING'}, f"Character {char_id}: failed to create plane")
                    continue

            img = _load_image_sequence(frames[0])
            if img is None:
                self.report(
                    {'WARNING'},
                    f"Character {char_id}: failed to load first frame {frames[0]}",
                )
                continue

            ok = _apply_image_sequence_material(obj, img, frame_count, ch_fps)
            if not ok:
                self.report(
                    {'WARNING'},
                    f"Character {char_id}: failed to build image-sequence material",
                )
                continue

            # 行走轨迹：多帧角色沿 X 从 walkFromX 线性走到 walkToX
            _add_walk_animation(obj, ch, frame_count)

            placed += 1
            if frame_count > max_frames:
                max_frames = frame_count
            used_fps = ch_fps

        # 时间线对齐：帧数 / fps → 末帧
        try:
            scene.render.fps = int(used_fps)
            scene.frame_start = 1
            scene.frame_end = max(1, max_frames)
        except Exception:
            pass

        self.report(
            {'INFO'},
            f"Imported {placed} character frame-sequence(s); timeline 1..{max_frames} @ {used_fps}fps",
        )
        return {'FINISHED'}
