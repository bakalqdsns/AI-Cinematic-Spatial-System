# -*- coding: utf-8 -*-
"""构造新项目的 manifest + pipeline_state，调 archive→render→compose 跑通单镜头。
严格走程序 API，不绕过 archive/render/compose endpoint。"""
import os, json, time, requests
from pathlib import Path

for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)

PROJ_ID = "20261004_人机协同测试"
PROJ = Path(r"F:\AICinematicSpatialSystem\backend\.workspace\projects") / PROJ_ID
BASE = "http://127.0.0.1:8001/api/aicss/v2"
s = requests.Session(); s.trust_env = False

# ── 1. 写 pipeline_state.json（单镜头 shot-3，5秒，李明） ──────────────
state = {
    "completed_steps": ["characters", "parse", "scenes", "shots", "motion"],
    "step": "archive",
    "project_id": PROJ_ID,
    "script_data": {
        "title": "人机协同测试",
        "genre": "drama",
        "logline": "李明推门进入咖啡馆（单镜头测试）",
        "characters": [
            {"id": "char-1", "name": "李明", "gender": "male", "age": "",
             "personality": "守时、略带焦虑", "visual_prompt": "", "reference_image": None}
        ],
        "scenes": [
            {"id": "scene-1", "location": "咖啡馆", "time": "Day",
             "atmosphere": "温馨", "estimated_shots": 1, "visual_prompt": ""}
        ],
        "story_paragraphs": [
            {"id": "para-1", "text": "李明推门而入，环顾四周，走向卡座",
             "scene_ref_id": "scene-1", "paragraph_type": "action",
             "speaker_id": "", "emotion": "", "contains_action": True}
        ],
        "language": "chinese"
    },
    "normalized_script": "李明推门而入，环顾四周，走向卡座",
    "raw_text": "李明推门而入，环顾四周，走向卡座",
    "shots": [
        {
            "id": "shot-3",
            "scene_id": "scene-1",
            "shot_number": 1,
            "action_summary": "李明推门而入，环顾四周，走向卡座",
            "dialogue": "",
            "camera_movement": "Tracking",
            "shot_size": "Medium Shot",
            "characters": ["char-1"],
            "visual_prompts": {
                "scene_prompt": "A cozy urban café interior, warm sunlight through tall windows, wooden tables, espresso machine, soft bokeh, no people, empty scene, cinematic composition, concept art background, high detail, dramatic lighting",
                "action_prompt": "A man in light gray shirt and canvas bag enters a café, scanning room, checking wristwatch, walking with purpose toward window booth, natural motion",
                "camera_prompt": "Steady tracking shot following from behind",
                "transition_prompt": ""
            },
            "duration_seconds": 5.0,
            "keyframe_start_prompt": "Man entering café, hand on door",
            "keyframe_end_prompt": "He sits down at window booth"
        }
    ]
}
(PROJ / "pipeline_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("[1] pipeline_state.json written", flush=True)

# ── 2. archive shot-3 ──────────────────────────────────────────────────
print("[2] archive shot-3...", flush=True)
r = s.post(f"{BASE}/projects/{PROJ_ID}/shots/shot-3/archive",
           params={"scene_id": "scene-1"}, timeout=3600, proxies={"http":None,"https":None})
print(f"   HTTP {r.status_code}: {r.text[:300]}", flush=True)
if r.status_code != 200:
    raise SystemExit(1)

# ── 3. render-queue shot-3 ──────────────────────────────────────────────
print("[3] render-queue shot-3...", flush=True)
r = s.post(f"{BASE}/projects/{PROJ_ID}/render-queue",
           json={"shotIds": ["shot-3"], "samples": 16, "resolution": [960, 540],
                 "device": "GPU", "fps": 24},
           timeout=1800, proxies={"http":None,"https":None})
render_resp = r.json()
print(f"   HTTP {r.status_code}: succeeded={render_resp.get('totalSucceeded')} failed={render_resp.get('totalFailed')}", flush=True)
for res in render_resp.get("results", []):
    print(f"     {res['shotId']}: {res['status']} {res.get('outputPath') or res.get('error','')[:120]}", flush=True)
if render_resp.get("totalSucceeded", 0) == 0:
    raise SystemExit(1)

# ── 4. compose ──────────────────────────────────────────────────────────
print("[4] compose...", flush=True)
succeeded = [r for r in render_resp.get("results", []) if r.get("status") == "succeeded"]
clip_paths = [r["outputPath"] for r in succeeded]
r = s.post(f"{BASE}/projects/{PROJ_ID}/compose",
           json={"clipPaths": clip_paths, "durations": [5.0],
                 "transition": "cut", "transitionDuration": 0.0},
           timeout=600, proxies={"http":None,"https":None})
print(f"   HTTP {r.status_code}", flush=True)
print(json.dumps(r.json(), ensure_ascii=False, indent=2), flush=True)
