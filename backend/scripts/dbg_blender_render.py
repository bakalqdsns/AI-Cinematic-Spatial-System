# -*- coding: utf-8 -*-
"""手动跑 Blender render_queue 看完整错误"""
import subprocess, sys, os, tempfile, json
from pathlib import Path

blender = r"F:\SteamLibrary\steamapps\common\Blender\blender.exe"
addon_parent = r"F:\AICinematicSpatialSystem\backend\blender\addons"
manifest = r"C:\Users\Administrator\AppData\Local\Temp\aicss_render_staging_if1swxpo\shot-1\manifest.json"
# 重新解压一个 manifest
import zipfile
proj = r"F:\AICinematicSpatialSystem\backend\.workspace\projects\20260927_055614_旧相册"
zip_path = Path(proj) / "archives" / "20260927_055614_旧相册_shot-1_archive.zip"
tmp = Path(tempfile.mkdtemp(prefix="aicss_dbg_"))
target = tmp / "shot-1"
target.mkdir()
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(target)
manifest = str(target / "manifest.json")
# 改短 duration 渲染快一点
import json as _j
_m = _j.load(open(manifest, encoding="utf-8"))
_m["duration"] = 0.2  # 5 frames @ 24fps
_j.dump(_m, open(manifest, "w", encoding="utf-8"), ensure_ascii=False)
print("manifest:", manifest, "exists:", os.path.exists(manifest), "duration=0.2s")

output_dir = str(tmp / "renders")
os.makedirs(output_dir, exist_ok=True)

script = f'''
import sys, os, json, traceback
import bpy
sys.path.insert(0, r"{addon_parent}")
print("===ADDON_IMPORT_START===", flush=True)
try:
    import aicss_scene_builder
    print("imported aicss_scene_builder OK", flush=True)
    aicss_scene_builder.register()
    print("register OK", flush=True)
except Exception as e:
    print("ADDON ERROR:", e, flush=True)
    traceback.print_exc()
    sys.exit(1)

print("===OPERATOR_START===", flush=True)
try:
    bpy.ops.aicss.render_queue(
        manifest_paths=r"{manifest}",
        output_dir=r"{output_dir}",
        project_id="20260927_055614_旧相册",
        samples=4,
        resolution_x=320,
        resolution_y=180,
        device="GPU",
        fps=24,
        lighting_preset="",
        continue_on_error=True,
    )
    print("===OPERATOR_DONE===", flush=True)
except Exception as e:
    print("===OPERATOR_ERROR:", e, flush=True)
    traceback.print_exc()

results_path = os.path.join(r"{output_dir}", "render_queue_results.json")
print("results_path:", results_path, "exists:", os.path.exists(results_path), flush=True)
if os.path.exists(results_path):
    print("===RESULTS_BEGIN===", flush=True)
    print(open(results_path, encoding="utf-8").read(), flush=True)
    print("===RESULTS_END===", flush=True)
'''
script_path = tmp / "dbg.py"
script_path.write_text(script, encoding="utf-8")
print("running blender...")
r = subprocess.run([blender, "--background", "--python", str(script_path)],
                   capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace")
print("===EXIT===", r.returncode)
print("===STDOUT===", r.stdout[-5000:] if r.stdout else "(empty)")
print("===STDERR===", r.stderr[-3000:] if r.stderr else "(empty)")
