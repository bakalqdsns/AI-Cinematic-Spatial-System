# -*- coding: utf-8 -*-
"""用归档清单装好层，渲正面、侧面、顶面、3/4、层分离和拆解视图。

视角列表和相机摆位在插件的 ``utils/view_presets.py``（纯 Python，
pytest 直接断言）。第 4 轮新增 front_three_quarter（3/4 视角）、
layer_separation（看层片缝隙）和 exploded（层片沿 X 拉开的拆解视图）。
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend\blender\addons")
import aicss_scene_builder
from aicss_scene_builder.utils import view_presets

aicss_scene_builder.register()

MANIFEST = os.environ["AICSS_MANIFEST"]
OUT = os.environ["AICSS_OUT"]
os.makedirs(OUT, exist_ok=True)

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.aicss.import_layers(manifest_path=MANIFEST, scene_width=20.0, scene_height=15.0)
bpy.ops.aicss.add_lighting(preset="warm_interior")

world = bpy.context.scene.world
if world is None:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
background = world.node_tree.nodes.get("Background")
if background:
    background.inputs["Color"].default_value = (0.55, 0.62, 0.7, 1.0)
    background.inputs["Strength"].default_value = 0.8

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.device = "GPU"
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.film_transparent = False
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "CUDA"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type != "CPU"
except Exception as exc:
    print("GPU_SETUP", exc)

layers = [obj for obj in bpy.data.objects if obj.get("aicss_layer")]
layout = []
for obj in layers:
    layout.append({
        "name": obj.get("aicss_layer"),
        "location": [round(v, 3) for v in obj.location],
        "rotationDeg": [round(math.degrees(v), 2) for v in obj.rotation_euler],
        "dimensions": [round(v, 2) for v in obj.dimensions],
        "modifiers": [mod.type for mod in obj.modifiers],
        "materials": [slot.name if slot else "" for slot in obj.data.materials],
    })
print("LAYER_LAYOUT " + json.dumps(layout, ensure_ascii=False))

if not layers:
    raise SystemExit("no layers imported")

zs = [obj.location.z for obj in layers]
center = Vector((0.0, 0.0, sum(zs) / len(zs)))
span = max(zs) - min(zs)

cam_data = bpy.data.cameras.new("MultiView")
cam_data.lens_unit = "FOV"
cam_data.angle = math.radians(35.0)
cam = bpy.data.objects.new("MultiView", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def aim(location, target):
    cam.location = location
    direction = Vector(target) - Vector(location)
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_view(name, extent_x=0.0):
    location, target = view_presets.view_camera(
        name, tuple(center), max(zs), span, extent_x=extent_x,
    )
    aim(location, target)
    scene.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("VIEW_OK", name, scene.render.filepath)


for name in view_presets.VIEW_NAMES:
    if name != "exploded":
        render_view(name)
        continue

    # 拆解视图：层片沿 X 方向拉开（远层在左、近层在右），渲完恢复原位。
    ordered = sorted(layers, key=lambda o: o.location.z)
    names = [obj.get("aicss_layer") for obj in ordered]
    offsets = view_presets.exploded_x_offsets(names)
    original = {obj.name: obj.location.copy() for obj in ordered}
    extent_x = 0.0
    for obj in ordered:
        dx = offsets[obj.get("aicss_layer")]
        obj.location.x = original[obj.name].x + dx
        # 用实际世界宽度估算布局半宽，让相机拉得足够远。
        extent_x = max(extent_x, abs(obj.location.x) + obj.dimensions.x / 2.0)
    render_view(name, extent_x=extent_x)
    for obj in ordered:
        obj.location = original[obj.name]
