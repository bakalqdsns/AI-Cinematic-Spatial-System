"""直接调用 mesh_exporter，打印 strip_billboards 的 diffuse_texture 值。"""
import sys, io, os, tempfile, logging
sys.path.insert(0, os.path.dirname(__file__))

# 开启 DEBUG 日志
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("aicss")

from pathlib import Path
from app.services.mesh_exporter import _prepare_textures, _serialize_scene_for_blender, SceneExportData
from app.services.mesh_exporter import _populate_strip_stack_into_scene

# 模拟 strip_stack 数据（从诊断脚本已知 billboardUrl 是 data: URL）
strip_stack = [
    {
        "regionId": "strip_0_foreground_person",
        "billboardUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==",  # 1x1 透明 PNG
        "inpaintResultUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==",
        "layerPolygon": [],
        "depthLayer": "foreground",
        "depthValue": 90,
        "colorIndex": 0,
    }
]

scene = SceneExportData(scene_id="debug_test", include_textures=True)
_populate_strip_stack_into_scene(scene, strip_stack)

print(f"\n=== Scene state after _populate_strip_stack_into_scene ===")
print(f"strip_billboards count: {len(scene.strip_billboards)}")
for bb in scene.strip_billboards:
    print(f"  region_id={bb.region_id} diffuse_texture={repr(bb.diffuse_texture)[:80]}")

print(f"\nbackground_plane: {scene.background_plane}")
if scene.background_plane:
    print(f"  texture={repr(scene.background_plane.texture)[:80]}")

# 模拟 _prepare_textures
with tempfile.TemporaryDirectory(prefix="aicss_debug_") as tmp:
    tmp_path = Path(tmp)
    texture_dir = _prepare_textures(scene, tmp_path)
    print(f"\n=== After _prepare_textures ===")
    print(f"texture_dir: {texture_dir}")
    if texture_dir.exists():
        files = list(texture_dir.glob("*"))
        print(f"texture files: {[f.name for f in files]}")
    for bb in scene.strip_billboards:
        print(f"  diffuse_texture now = {repr(bb.diffuse_texture)[:80]}")
    if scene.background_plane:
        print(f"  bg texture now = {repr(scene.background_plane.texture)[:80]}")

    # 生成 blender 脚本
    script = open(tmp_path / "export_scene.py", "w", encoding="utf-8")
    blender_script_text = None
    # Patch _generate_blender_script to return text
    from app.services import mesh_exporter as me
    blender_script_text = me._generate_blender_script(scene)
    script.write(blender_script_text)
    script.close()

    # 检查脚本中 strip_billboards 的 diffuse_texture
    text = blender_script_text
    idx = text.find("strip_billboards")
    if idx >= 0:
        end = text.find("]", idx)
        print(f"\n=== Blender script strip_billboards section ===")
        print(text[idx:end+1][:2000])
    
    # 检查 scene_data.json
    json_text = me._serialize_scene_for_blender(scene)
    j = __import__("json").loads(json_text)
    print(f"\n=== scene_data.json strip_billboards ===")
    for bb in j.get("strip_billboards", []):
        print(f"  region_id={bb['region_id']} diffuse_texture={repr(bb.get('diffuse_texture',''))[:80]}")
    print(f"background_plane: {j.get('background_plane', {})}")
