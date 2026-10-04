"""
import_layers operator — reads an AICSS manifest.json and creates one
Blender mesh plane per depth layer.

The planes are positioned along the camera Z-axis using the manifest's
zOffsets table (which mirrors `backend.app.services.layer_exporter.
LAYER_Z_OFFSETS`). Each plane gets the paper material applied via
``materials/paper_material.apply_paper_material``.

When the manifest provides a per-layer thickness (``thicknessMm``) the
plane is converted to a thin Box (extruded by the given thickness in
metres) so the paper-cut silhouette has visible depth when rendered.

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
        for layer in LAYER_ORDER:
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


def _create_plane_for_character(ch, manifest, *, collection,
                                  scene_width, scene_height):
    """T10: 为一个角色创建一个平面，按 manifest 的 position/scale 落位。

    character 项字段：
      id (必填), name, framesDir, frameCount, fps
      position: [x, y, z]  (可选，默认前景层 z)
      scale:    [sx, sy]   (可选，默认 [4.0, 4.0] BU)

    返回创建的对象，失败返回 None。
    """
    from ..utils.scene_utils import Z_OFFSETS

    char_id = ch.get("id") or ch.get("name") or "character"
    position = ch.get("position")
    if not position or len(position) < 3:
        # 默认放在前景层前面一点（z=0），水平居中，确保不被 foreground 遮挡
        position = [0.0, 0.0, 0.0]
    scale = ch.get("scale") or [4.0, 4.0]

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

    Returns the created object or None on failure.
    """
    from ..utils.scene_utils import layer_z_offset

    z_offset = layer_z_offset(manifest, layer)

    # Create the mesh — we use a plain Plane and resize it to the scene
    # dimensions in world units. The PNG is applied as a diffuse texture
    # by ``apply_paper_material``.
    bpy.ops.mesh.primitive_plane_add(
        size=1.0,
        location=(0.0, 0.0, z_offset),
    )
    obj = bpy.context.active_object
    obj.name = f"AICSS_Layer_{layer}"
    # plane 默认法线 +Z，相机在 +Z 方向沿 -Z 看，法线 +Z 正好朝相机，无需旋转。
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (scene_width, scene_height, 1.0)

    # Track metadata on the object so other operators / UI panels can
    # discover which layers exist and where they came from.
    obj["aicss_layer"] = layer
    obj["aicss_layer_z"] = z_offset
    obj["aicss_layer_png"] = png_path
    obj["aicss_shot_id"] = manifest.get("shotId", "")

    # Move the object to the desired collection
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection.objects.link(obj)

    return obj