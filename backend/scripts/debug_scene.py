# -*- coding: utf-8 -*-
"""诊断脚本：构造 shot-3 场景，保存 .blend 文件 + dump 所有对象/材质/相机细节。
不渲染，只建场景，方便在 Blender GUI 打开调试。"""
import sys, os, json, math
sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend\blender\addons")
import bpy
import aicss_scene_builder
aicss_scene_builder.register()

MANIFEST = r"F:\AICinematicSpatialSystem\backend\.workspace\projects\20261004_人机协同测试\archives\_extract\manifest.json"
OUT = r"F:\AICinematicSpatialSystem\backend\.workspace\projects\20261004_人机协同测试\renders\debug_scene"
os.makedirs(OUT, exist_ok=True)

# 清场景
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# 装载
bpy.ops.aicss.import_layers(manifest_path=MANIFEST)
bpy.ops.aicss.setup_camera_animation(manifest_path=MANIFEST, fps=24.0)
bpy.ops.aicss.add_lighting(preset="warm_interior")

# 提高环境光
w = bpy.context.scene.world
if w is None:
    w = bpy.data.worlds.new("W"); bpy.context.scene.world = w
w.use_nodes = True
bg = w.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 1.5

# dump 对象详情
print("=" * 60)
print("SCENE OBJECTS")
print("=" * 60)
for o in bpy.data.objects:
    loc = tuple(round(x, 3) for x in o.location)
    rot = tuple(round(math.degrees(x), 1) for x in o.rotation_euler)
    scl = tuple(round(x, 3) for x in o.scale)
    print(f"\n[{o.name}] type={o.type}")
    print(f"  loc={loc} rot_deg={rot} scale={scl}")
    if o.type == 'MESH':
        # bounding box (world)
        bbox = [o.matrix_world @ __import__('mathutils').Vector(corner) for corner in o.bound_box]
        xs = [v.x for v in bbox]; ys = [v.y for v in bbox]; zs = [v.z for v in bbox]
        print(f"  bbox: x=[{min(xs):.2f},{max(xs):.2f}] y=[{min(ys):.2f},{max(ys):.2f}] z=[{min(zs):.2f},{max(zs):.2f}]")
        # 法线方向
        if o.data.vertices:
            n = o.data.vertices[0].normal
            wn = o.matrix_world.to_3x3() @ n
            print(f"  vert0 normal (world): ({wn.x:.2f}, {wn.y:.2f}, {wn.z:.2f})")
        # 材质
        for slot in o.material_slots:
            if slot.material:
                print(f"  material: {slot.material.name}")
                tree = slot.material.node_tree
                for n in tree.nodes:
                    if n.type == 'TEX_IMAGE' and n.image:
                        print(f"    tex image: {n.image.name} {n.image.size[0]}x{n.image.size[1]} alpha={n.image.depth==32}")
    elif o.type == 'CAMERA':
        print(f"  lens={o.data.lens}mm fov={math.degrees(o.data.angle):.1f}deg")
        print(f"  is_scene_cam={bpy.context.scene.camera == o}")
        for c in o.constraints:
            print(f"  constraint: {c.type} target={c.target.name if c.target else None}")

# dump 灯光
print("\n" + "=" * 60)
print("LIGHTS")
print("=" * 60)
for o in bpy.data.objects:
    if o.type == 'LIGHT':
        ld = o.data
        print(f"[{o.name}] type={ld.type} energy={ld.energy} loc={tuple(round(x,2) for x in o.location)}")

# dump world
print("\n" + "=" * 60)
print("WORLD")
print("=" * 60)
w = bpy.context.scene.world
if w and w.use_nodes:
    bg = w.node_tree.nodes.get("Background")
    if bg:
        print(f"  bg color={tuple(round(x,2) for x in bg.inputs['Color'].default_value)} strength={bg.inputs['Strength'].default_value}")

# 保存 .blend
blend_path = os.path.join(OUT, "shot-3_debug.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"\n[SAVED] {blend_path}")

# 也导出每个 mesh 为 OBJ（方便其他工具查看）
import shutil
for o in bpy.data.objects:
    if o.type == 'MESH':
        # 选中并激活
        for x in bpy.context.selected_objects:
            x.select_set(False)
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        obj_path = os.path.join(OUT, f"{o.name}.obj")
        try:
            bpy.ops.wm.obj_export(filepath=obj_path, export_selected_objects=True, export_materials=True)
            print(f"[OBJ] {obj_path}")
        except Exception as e:
            print(f"[OBJ FAIL] {o.name}: {e}")

print("===DONE===")
