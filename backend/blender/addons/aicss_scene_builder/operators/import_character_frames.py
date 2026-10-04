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
    """返回 framesDir 下排序后的 frame_*.png 绝对路径列表。"""
    if not frames_dir or not os.path.isdir(frames_dir):
        return []
    try:
        frames = sorted(
            f for f in os.listdir(frames_dir)
            if f.lower().endswith(".png")
        )
    except Exception:
        return []
    # 优先 frame_*.png，否则任何 png
    frame_named = [f for f in frames if f.lower().startswith("frame_")]
    if frame_named:
        frames = frame_named
    return [os.path.join(frames_dir, f) for f in frames]


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
    from ..utils.scene_utils import Z_OFFSETS

    char_id = char.get("id") or char.get("name") or "character"
    position = char.get("position")
    if not position or len(position) < 3:
        position = [0.0, 0.0, Z_OFFSETS["foreground"]]
    scale = char.get("scale") or [4.0, 4.0]

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
            frameCount, fps, position?, scale?}``.
        fps: Override the manifest's per-character fps (default 0 = read
            from manifest, fallback 24).
        default_scale: Plane scale used when manifest has no ``scale`` field
            (default [4.0, 4.0] BU).
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
        default=4.0,
        min=0.1,
        max=50.0,
        description="Plane scale used when manifest has no `scale` field",
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
