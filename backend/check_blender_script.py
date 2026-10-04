"""Find the persistent mesh directory and check for any Blender scripts."""
import json, tempfile, glob, os
from pathlib import Path

persist = Path(os.environ.get(
    "AICSS_MESH_PERSIST_DIR",
    str(Path(tempfile.gettempdir()) / "aicss_mesh_persist"),
))
print(f"Persist dir: {persist}")
if persist.exists():
    files = list(persist.glob("*"))
    print(f"Files: {files[:10]}")
    
# Also search for export_scene.py anywhere in temp
search = Path(tempfile.gettempdir())
print(f"\nSearching in {search} for aicss_mesh_ directories:")
for d in search.glob("aicss_mesh_*"):
    script = d / "export_scene.py"
    if script.exists():
        print(f"  Found: {script}")
        text = script.read_text(encoding="utf-8")
        idx = text.find("strip_billboards")
        if idx >= 0:
            print(text[idx:idx+3000])
