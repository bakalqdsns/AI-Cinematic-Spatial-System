"""
import_layers operator — reads an AICSS manifest.json and creates one
Blender mesh plane per depth layer.

The planes are positioned along the camera Z-axis using the manifest's
zOffsets table (which mirrors `backend.app.services.layer_exporter.
LAYER_Z_OFFSETS`). Each plane gets the paper material applied via
``materials/paper_material.apply_paper_material``.

第 4 轮「分层明显化」：每张层片按清单的纸雕呈现字段
（thicknessM / yawDeg / pitchDeg / shiftXM / shiftYM，缺省值见
``utils/scene_utils.py``）做三件事 —— 水平错位、轻微偏航/俯仰、
Solidify 沿背面挤出厚度。挤出的 rim 面用共享的「切边」材质
（``materials/paper_material.apply_paper_edge_material``），再加
小 Bevel 让切边吃光，层与层之间在静止帧里也能看出纸片感。
深度归层语义不变：正面位置仍由 zOffset 决定。

Outside Blender the operator class is still importable but registers as
a no-op (see ``__init__.py``).
"""
from __future__ import annotations

import os

# bpy is Blender's Python API. It's only present when running inside
# Blender; in unit-test / CI environments we no-op so the module can be
# imported without Blender installed.
try:
    import bpy
    from bpy.types import Operator
    from bpy.props import StringProperty, FloatProperty, BoolProperty
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False

    # Minimal stubs so the class body parses outside Blender. The class
    # never gets registered when bpy is missing so the stubs are inert.
    class Operator:  # type: ignore[no-redef]
        pass

    def StringProperty(**kw): return None  # type: ignore[no-redef]
    def FloatProperty(**kw): return None  # type: ignore[no-redef]
    def BoolProperty(**kw): return None  # type: ignore[no-redef]


class AICSS_OT_import_layers(Operator):
    """Import AICSS layer PNGs and assemble a paper-diorama scene.

    Properties:
        manifest_path: Path to the manifest.json exported by the backend.
        scene_width: World-space scene width in Blender units.
        scene_height: World-space scene height in Blender units.
        apply_paper_material: If True, run the paper-material operator
            on every imported plane so they get the diffuse + normal map.
        create_collection: Wrap the imported objects in a new Blender
            collection named after ``manifest.shotId``.
    """
    bl_idname = "aicss.import_layers"
    bl_label = "Import AICSS Layers"
    bl_options = {'REGISTER', 'UNDO'}

    manifest_path: StringProperty(
        name="Manifest Path",
        description="Path to the AICSS manifest.json",
        subtype='FILE_PATH',
    )
    scene_width: FloatProperty(
        name="Scene Width",
        default=20.0,
        min=1.0,
        max=200.0,
        description="World width of the scene in Blender units",
    )
    scene_height: FloatProperty(
        name="Scene Height",
        default=15.0,
        min=1.0,
        max=200.0,
        description="World height of the scene in Blender units",
    )
    apply_paper_material: BoolProperty(
        name="Apply Paper Material",
        default=True,
    )
    create_collection: BoolProperty(
        name="Create Collection",
        default=True,
    )

    def execute(self, context):
        if not _HAS_BPY:
            self.report({'ERROR'}, "bpy not available — run inside Blender")
            return {'CANCELLED'}

        if not self.manifest_path or not os.path.exists(self.manifest_path):
            self.report({'ERROR'}, f"Manifest not found: {self.manifest_path}")
            return {'CANCELLED'}

        # Local imports so non-Blender environments don't fail
        from ..utils.scene_utils import (
            read_manifest, layer_z_offset, LAYER_ORDER,
        )
        from ..materials.paper_material import apply_paper_material

        try:
            manifest = read_manifest(self.manifest_path)
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to read manifest: {exc}")
            return {'CANCELLED'}

        # Create / reuse a collection so the imported objects stay grouped
        coll_name = f"AICSS_{manifest['shotId']}"
        if self.create_collection:
            collection = bpy.data.collections.get(coll_name)
            if collection is None:
                collection = bpy.data.collections.new(coll_name)
            if collection.name not in [c.name for c in context.scene.collection.children]:
                context.scene.collection.children.link(collection)
        else:
            collection = context.scene.collection

        imported = []
        manifest_dir = os.path.dirname(os.path.abspath(self.manifest_path))
        layer_names = list(LAYER_ORDER) + [
            name for name in manifest["layers"].keys() if name not in LAYER_ORDER
        ]
        for layer in layer_names:
            png_path = manifest["layers"].get(layer)
            if not png_path:
                continue
            # Resolve relative paths against the manifest directory
            if not os.path.isabs(png_path):
                png_path = os.path.join(manifest_dir, png_path)
            if not os.path.exists(png_path):
                # Layer is optional (e.g. sky for night scenes) — skip silently.
                continue
            obj = _create_plane_for_layer(
                layer, png_path, manifest,
                scene_width=self.scene_width,
                scene_height=self.scene_height,
                collection=collection,
            )
            if obj is None:
                self.report({'WARNING'}, f"Failed to import layer {layer}: {png_path}")
                continue
            imported.append((layer, obj))

            if self.apply_paper_material:
                apply_paper_material(obj, image_path=png_path)
            # 纸面材质之后再加厚度和切边：apply_paper_material 会把所有
            # 材质槽换成纸面材质，切边槽必须在那之后追加。
            _add_card_thickness(obj, layer, manifest)

        if not imported:
            self.report({'ERROR'}, "No layers were imported — check the manifest")
            return {'CANCELLED'}

        # ── 角色：读 manifest 的 characters[]，创建平面 + 应用纸张材质 ──────
        # T10: 每个 character 项含 {id, name, framesDir, frameCount, fps}，
        # 可选 position/scale。我们在指定坐标创建一个 plane，贴上 framesDir
        # 下的第一帧 PNG 作为静态贴图（动画播放由 T08 的 import_character_frames
        # operator 负责，这里只做"落位"）。
        characters = manifest.get("characters") or []
        placed_chars = 0
        for ch in characters:
            try:
                obj = _create_plane_for_character(
                    ch, manifest, collection=collection,
                    scene_width=self.scene_width,
                    scene_height=self.scene_height,
                )
            except Exception as exc:
                self.report({'WARNING'}, f"Failed to place character {ch.get('id')}: {exc}")
                continue
            if obj is not None:
                placed_chars += 1
                if self.apply_paper_material:
                    # 用 framesDir 下第一帧作为贴图（静态落位）
                    frames_dir = ch.get("framesDir", "")
                    first_png = _first_frame_in_dir(frames_dir)
                    if first_png:
                        apply_paper_material(obj, image_path=first_png)

        if placed_chars:
            self.report(
                {'INFO'},
                f"Placed {placed_chars} character plane(s)",
            )

        # Set the active scene camera if one already exists (don't create
        # a camera here — that's the job of setup_camera).
        self.report(
            {'INFO'},
            f"Imported {len(imported)} layers for shot {manifest['shotId']}",
        )
        return {'FINISHED'}


def _first_frame_in_dir(frames_dir: str) -> str:
    """返回 framesDir 下中间帧的绝对路径（角色通常在中间最完整），找不到返回 ""。"""
    if not frames_dir:
        return ""
    try:
        if not os.path.isdir(frames_dir):
            return ""
        frames = sorted(
            f for f in os.listdir(frames_dir)
            if f.lower().endswith(".png") and f.lower().startswith("frame_")
        )
        if not frames:
            # 退而求其次：任何 png
            frames = sorted(f for f in os.listdir(frames_dir) if f.lower().endswith(".png"))
        if not frames:
            return ""
        # 用中间帧（角色通常在中间最完整，第一帧可能刚入画被切边）
        mid = len(frames) // 2
        return os.path.join(frames_dir, frames[mid])
    except Exception:
        return ""


# 人物默认身高（米）与帧内占比：清单没写 scale 时按 1.6m 人物、
# 人物占帧高度九成估算平面高度，不再拍脑袋 4.0。
DEFAULT_CHARACTER_HEIGHT_M = 1.6
DEFAULT_CHARACTER_FILL = 0.9
# 人物平面贴在地面层靠相机一侧的距离（米），避免和地面卡片共面闪面。
# 只作旧回退：ground==foreground 等退化情况使用。
CHARACTER_GROUND_CLEARANCE_M = 0.3
# 人物平面深度：foreground 与 ground 之间、从前景往地面走的比例。
# 与后端 shot_archiver._CHARACTER_DEPTH_FROM_FOREGROUND 一致（0.35 →
# 当前分层约 -7.0m），人物在画面里够大，又仍在前景之后不悬空。
CHARACTER_DEPTH_FROM_FOREGROUND = 0.35


def _manifest_layer_z(manifest, layer, fallback):
    """不依赖包结构地查清单里某层的 zOffset（scene_utils.layer_z_offset
    的独立副本，供本模块被单独加载时使用）。"""
    for entry in manifest.get("zOffsets", []):
        if entry.get("layer") == layer:
            try:
                return float(entry.get("zOffset"))
            except (TypeError, ValueError):
                break
    return float(fallback)


def default_character_z(manifest):
    """人物默认深度：ground 与 foreground 之间靠前景 0.35 处（镜像后端）。

    两层都查得到时按比例插值并夹到层间（留共面清隙）；退化时回退到
    地面层 + CHARACTER_GROUND_CLEARANCE_M。
    """
    try:
        from ..utils.scene_utils import layer_z_offset
        ground = layer_z_offset(manifest, "ground")
        foreground = layer_z_offset(manifest, "foreground")
    except ImportError:
        # 模块被单独加载（无包上下文）时直接读清单
        ground = _manifest_layer_z(manifest, "ground", -4.0)
        foreground = _manifest_layer_z(manifest, "foreground", -2.0)
    if ground == foreground:
        return ground + CHARACTER_GROUND_CLEARANCE_M
    z = foreground + (ground - foreground) * CHARACTER_DEPTH_FROM_FOREGROUND
    lo, hi = sorted((ground, foreground))
    clearance = min(CHARACTER_GROUND_CLEARANCE_M, abs(hi - lo) / 4.0)
    return min(max(z, lo + clearance), hi - clearance)


def _create_plane_for_character(ch, manifest, *, collection,
                                  scene_width, scene_height):
    """T10: 为一个角色创建一个平面，按 manifest 的 position/scale 落位。

    character 项字段：
      id (必填), name, framesDir, frameCount, fps
      position: [x, y, z]  (可选，默认 ground 与 foreground 之间靠前景 0.35 处)
      scale:    [sx, sy]   (可选，默认按 1.6m 人物占帧九成 ≈ [1.78, 1.78])

    返回创建的对象，失败返回 None。
    """
    char_id = ch.get("id") or ch.get("name") or "character"
    position = ch.get("position")
    if not position or len(position) < 3:
        # 默认深度与后端一致：ground 与 foreground 之间靠前景 0.35 处，
        # 人物在画面里够大，仍落在地面层之前不悬空
        position = [0.0, 0.0, default_character_z(manifest)]
    scale = ch.get("scale")
    if not scale or len(scale) < 2:
        s = DEFAULT_CHARACTER_HEIGHT_M / DEFAULT_CHARACTER_FILL
        scale = [round(s, 3), round(s, 3)]

    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(float(position[0]), float(position[1]), float(position[2])),
    )
    obj = bpy.context.active_object
    obj.name = f"AICSS_Character_{char_id}"
    # 与 layer plane 一致：法线朝 +Z（朝相机，相机在 +Z 方向）
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (float(scale[0]), float(scale[1]), 1.0)

    obj["aicss_role"] = "character"
    obj["aicss_character_id"] = str(char_id)
    obj["aicss_character_name"] = str(ch.get("name", char_id))
    obj["aicss_frames_dir"] = str(ch.get("framesDir", ""))
    obj["aicss_frame_count"] = int(ch.get("frameCount", 0) or 0)
    obj["aicss_fps"] = int(ch.get("fps", 24) or 24)
    obj["aicss_shot_id"] = manifest.get("shotId", "")

    # 移到目标 collection
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection.objects.link(obj)

    return obj


def _create_plane_for_layer(layer, png_path, manifest, *,
                             scene_width, scene_height, collection):
    """Create a plane mesh for a single layer, position it on the Z-axis,
    and link it to ``collection``.

    第 4 轮：在 Z 定位之外按清单的纸雕呈现字段加水平错位和轻微
    偏航/俯仰（默认见 scene_utils），让卡片不再全部正对相机。
    最后把缩放烘进网格，Solidify/Bevel 的厚度、宽度才能按米走。

    Returns the created object or None on failure.
    """
    import math

    from ..utils.scene_utils import (
        layer_pitch_deg, layer_plane_scale, layer_shift,
        layer_yaw_deg, layer_z_offset,
    )

    z_offset = layer_z_offset(manifest, layer)
    plane_scale = layer_plane_scale(manifest, layer)
    shift_x, shift_y = layer_shift(manifest, layer)
    yaw_deg = layer_yaw_deg(manifest, layer)
    pitch_deg = layer_pitch_deg(manifest, layer)

    # Create the mesh — we use a plain Plane and resize it to the scene
    # dimensions in world units. The PNG is applied as a diffuse texture
    # by ``apply_paper_material``.
    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(shift_x, shift_y, z_offset),
    )
    obj = bpy.context.active_object
    obj.name = f"AICSS_Layer_{layer}"
    # plane 默认法线 +Z，相机在 +Z 方向沿 -Z 看，法线 +Z 正好朝相机。
    # 加轻微偏航/俯仰（全部同向、幅度差 ≤0.5°，相邻层不会穿插），
    # 让卡片边缘在运镜和斜视时露出来。
    obj.rotation_euler = (
        math.radians(pitch_deg),
        math.radians(yaw_deg),
        0.0,
    )
    obj.scale = (scene_width * plane_scale, scene_height * plane_scale, 1.0)
    # 把缩放烘进网格：之后 Solidify 厚度、Bevel 宽度按米计算，
    # 不会被非均匀缩放拉歪。失败也不致命，只是切角略不均匀。
    scale_applied = False
    try:
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        scale_applied = True
    except Exception:
        scale_applied = False
    obj["aicss_layer_scale"] = plane_scale
    obj["aicss_scale_applied"] = scale_applied

    # Track metadata on the object so other operators / UI panels can
    # discover which layers exist and where they came from.
    obj["aicss_layer"] = layer
    obj["aicss_layer_z"] = z_offset
    obj["aicss_layer_png"] = png_path
    obj["aicss_layer_yaw_deg"] = yaw_deg
    obj["aicss_layer_pitch_deg"] = pitch_deg
    obj["aicss_layer_shift"] = [shift_x, shift_y]
    obj["aicss_shot_id"] = manifest.get("shotId", "")

    # Move the object to the desired collection
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection.objects.link(obj)

    return obj


def _add_card_thickness(obj, layer, manifest) -> None:
    """把零厚度的层片变成纸雕卡片：Solidify 挤出厚度 + 切边材质 + 小切角。

    Solidify 沿背面挤出（offset=-1），正面位置不动，zOffset 语义不变。
    挤出的 rim 面用共享的「切边」材质（暖纸板色），让卡片边缘一眼能
    看出是剪下来的纸；再补一个小 Bevel，切边在灯下有一条细高光。
    任何一步失败都只损失装饰，不影响层片本身。

    必须在 ``apply_paper_material`` 之后调用 —— 它会把所有材质槽换成
    纸面材质，切边槽要在这之后追加。
    """
    from ..materials.paper_material import apply_paper_edge_material
    from ..utils.scene_utils import layer_thickness

    try:
        thickness = layer_thickness(manifest, layer)
    except Exception:
        thickness = 0.08

    try:
        edge_slot = apply_paper_edge_material(obj)
    except Exception:
        edge_slot = 0

    try:
        solidify = obj.modifiers.new(name="AICSS_CardThickness", type='SOLIDIFY')
        solidify.thickness = thickness
        solidify.offset = -1.0
        # rim（卡片四周的切边）用切边材质槽；背面仍用纸面材质。
        solidify.material_offset_rim = edge_slot
    except Exception:
        return

    # 缩放已烘进网格时 Bevel 宽度才是均匀的米；否则切角会被拉歪，宁可不加。
    try:
        if obj.get("aicss_scale_applied"):
            bevel = obj.modifiers.new(name="AICSS_CardEdge", type='BEVEL')
            bevel.width = min(0.02, thickness * 0.3)
            bevel.segments = 2
            bevel.limit_method = 'ANGLE'
    except Exception:
        pass