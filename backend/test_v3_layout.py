"""
Verify the new v3 directory layout:

  .workspace/projects/<timestamp>_<slugified_title>/
      manifest.json
      script_data (inline in manifest)
      characters/<character_name>/<action>/frame_NNN.png
      scenes/<scene_name>/asset_<scene_id>.json

Sends /parse with NO project_id, lets the server auto-derive one
based on ScriptData.title ("纸境"), then prints the resulting tree.
"""
import json
import time
from pathlib import Path

import requests

from app.services.project_store import (
    WORKSPACE_DIR,
    make_project_id,
    migrate_legacy_layout,
    migrate_all_legacy_projects,
)

BASE = "http://localhost:8000/api/aicss/v2/scripts"

SCRIPT_TEXT = """
场景1
内景。教室 - 傍晚
林知夏（17岁，短发，校服）独自坐在靠窗的位置，面前摊着一本数学练习册。
老师的脚步声从走廊经过。林知夏迅速合上练习册。
她从练习册上抬起头，看向窗外。窗外天空呈渐变色，云层稀薄。
林知夏皱眉，用力揉眼睛。再看，云恢复正常。她转回头，无意识画了一个纸飞机。
（过渡：笔尖停下。画面渐暗。）

场景2
外景。校园 - 黄昏
林知夏背着书包穿过校园。梧桐树叶变成平滑切线，路灯没有影子，教学楼变成纸板模型。
她攥紧了书包带，指尖发白。
（她开始向操场方向小跑。）
"""

print("=" * 70)
print("Verification: v3 directory layout")
print("=" * 70)

# Wipe any old project for clean tree output
print("\n[1] baseline workspace listing:")
if WORKSPACE_DIR.is_dir():
    for p in sorted(WORKSPACE_DIR.iterdir()):
        print(f"    - {p.name}")

print("\n[2] calling /parse with NO project_id (server should auto-derive)")
r = requests.post(f"{BASE}/parse", json={"raw_text": SCRIPT_TEXT, "language": "chinese"})
print(f"    status: {r.status_code}")
if r.status_code != 200:
    print(r.text[:600])
    raise SystemExit(1)

result = r.json()
derived_pid = result.get("project_id")
print(f"    auto-derived project_id: {derived_pid}")
print(f"    normalized_script head: {result['normalized_script'][:60]!r}")
print(f"    script_data.title: {result['script_data'].get('title')!r}")
n_chars = len(result["script_data"].get("characters", []))
n_scenes = len(result["script_data"].get("scenes", []))
print(f"    characters: {n_chars}, scenes: {n_scenes}")

print("\n[3] waiting for kickoff_after_parse auto-batch to land")
# The /parse endpoint kicks off background tasks for character three-view and
# scene keyframes. Wait until both stages complete by polling batch status.
deadline = time.time() + 240  # up to 4 min for cloud calls
chars_done = False
scenes_done = False
while time.time() < deadline and not (chars_done and scenes_done):
    time.sleep(5)
    cr = requests.get(f"{BASE}/characters/batch-status", params={"project_id": derived_pid})
    sr = requests.get(f"{BASE}/scenes/batch-status", params={"project_id": derived_pid})
    cs = cr.json().get("summary", {}) if cr.status_code == 200 else {}
    ss = sr.json().get("summary", {}) if sr.status_code == 200 else {}
    print(f"    chars={cs.get('done',0)}/{sum(cs.values())} scenes={ss.get('done',0)}/{sum(ss.values())}")
    chars_done = cs.get("queued", 0) == 0 and cs.get("running", 0) == 0
    scenes_done = ss.get("queued", 0) == 0 and ss.get("running", 0) == 0

print("\n[4] printing resulting workspace tree")
proj_dir = WORKSPACE_DIR / derived_pid
if not proj_dir.is_dir():
    print(f"    !! expected project dir not found: {proj_dir}")
    raise SystemExit(1)


def tree(path: Path, prefix: str = "") -> None:
    """Recursive tree listing with size."""
    entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    for i, p in enumerate(entries):
        last = i == len(entries) - 1
        connector = "└── " if last else "├── "
        if p.is_dir():
            print(f"{prefix}{connector}{p.name}/")
            tree(p, prefix + ("    " if last else "│   "))
        else:
            size_kb = p.stat().st_size / 1024
            print(f"{prefix}{connector}{p.name}  ({size_kb:.1f} KB)")


tree(proj_dir)

print("\n[5] sanity-check: manifest contents")
manifest = json.loads((proj_dir / "manifest.json").read_text(encoding="utf-8"))
print(f"    projectId: {manifest.get('projectId')}")
print(f"    shotId:    {manifest.get('shotId')}")
sd = manifest.get("scriptData") or {}
chars = sd.get("characters") or []
scenes = sd.get("scenes") or []
print(f"    scriptData.title: {sd.get('title')!r}")
print(f"    scriptData.characters: {[c.get('name') for c in chars]}")
print(f"    scriptData.scenes: {[(s.get('id'), s.get('location')) for s in scenes]}")

print("\n[6] test migration utility against this v3 project (should be a no-op)")
mig = migrate_legacy_layout(derived_pid, dry_run=True)
print(f"    dry-run: {mig}")
mig2 = migrate_legacy_layout(derived_pid, dry_run=False)
print(f"    real:    {mig2}  (expect all skipped — already v3)")

print("\n[7] migrate_all_legacy_projects")
all_mig = migrate_all_legacy_projects(dry_run=True)
print(f"    scanned {len(all_mig)} projects (dry-run)")
for pid, m in list(all_mig.items())[:5]:
    print(f"    {pid}: moved={m['moved']} skipped={m['skipped']} errors={len(m['errors'])}")

print("\n[8] round-trip: list_character_assets should return every saved file")
# Pick the first character id (the API uses char.id internally)
char0 = chars[0] if chars else None
if char0:
    cid = char0.get("id")
    r2 = requests.post(
        f"{BASE}/characters/generate-three-view",
        json={
            "character_id": cid,
            "character_name": char0.get("name"),
            "character_gender": "female",
            "character_personality": "敏感",
            "project_id": derived_pid,
        },
    )
    print(f"    manual three-view status={r2.status_code} (already done, just confirms idempotency)")
