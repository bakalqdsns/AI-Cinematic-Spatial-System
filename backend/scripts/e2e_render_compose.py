# -*- coding: utf-8 -*-
"""完整 E2E: 14 shot archive + render + compose（低参数快速验证）"""
import os, json, time, requests
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)
PROJECT_ID = "20260927_055614_旧相册"
BASE = "http://127.0.0.1:8001/api/aicss/v2"
s = requests.Session(); s.trust_env = False

shot_ids = [f"shot-{i}" for i in range(1, 15)]
scene_map = {1:"scene-1",2:"scene-1",3:"scene-1",4:"scene-1",5:"scene-1",6:"scene-1",
             7:"scene-1",8:"scene-1",9:"scene-1",10:"scene-2",11:"scene-2",12:"scene-2",
             13:"scene-2",14:"scene-2"}

# 1. 重新生成 14 个 archive（带 layers）
print("=== ARCHIVE ===", flush=True)
for i, sid in enumerate(shot_ids, 1):
    r = s.post(f"{BASE}/projects/{PROJECT_ID}/shots/{sid}/archive",
               params={"scene_id": scene_map[i]}, timeout=120, proxies={"http":None,"https":None})
    print(f"  ({i}/14) {sid}: {r.status_code} layers={r.json().get('layerCount')}", flush=True)

# 2. render-queue 14 shot（低 samples 小分辨率）
print("=== RENDER ===", flush=True)
r = s.post(f"{BASE}/projects/{PROJECT_ID}/render-queue",
           json={"shotIds": shot_ids, "samples": 4, "resolution": [320, 180],
                 "device": "GPU", "fps": 24},
           timeout=1800, proxies={"http":None,"https":None})
render_resp = r.json()
print(f"  HTTP {r.status_code}: succeeded={render_resp.get('totalSucceeded')} failed={render_resp.get('totalFailed')}", flush=True)
for res in render_resp.get("results", []):
    print(f"    {res['shotId']}: {res['status']} {res.get('outputPath') or res.get('error','')[:80]}", flush=True)

# 3. compose
print("=== COMPOSE ===", flush=True)
succeeded = [r for r in render_resp.get("results", []) if r.get("status") == "succeeded"]
if not succeeded:
    print("  no succeeded shots — skip compose", flush=True)
    raise SystemExit(1)
clip_paths = [r["outputPath"] for r in succeeded]
durations = [3.0] * len(clip_paths)  # 简化：每个 3 秒
r = s.post(f"{BASE}/projects/{PROJECT_ID}/compose",
           json={"clipPaths": clip_paths, "durations": durations,
                 "transition": "cut", "transitionDuration": 0.0},
           timeout=600, proxies={"http":None,"https":None})
print(f"  HTTP {r.status_code}", flush=True)
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:1000], flush=True)
