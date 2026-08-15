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
        for layer in LAYER_ORDER:
            png_path = manifest["layers"].get(layer)
            if not png_path or not os.path.exists(png_path):
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

        # Set the active scene camera if one already exists (don't create
        # a camera here — that's the job of setup_camera).
        self.report(
            {'INFO'},
            f"Imported {len(imported)} layers for shot {manifest['shotId']}",
        )
        return {'FINISHED'}


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