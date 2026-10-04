# -*- coding: utf-8 -*-
"""重新生成 shot-1 archive + 跑 render-queue shot-1 测试"""
import os, json, requests, sys
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)
PROJECT_ID = "20260927_055614_旧相册"
BASE = "http://127.0.0.1:8001/api/aicss/v2"
s = requests.Session(); s.trust_env = False

# 1. 重新生成 shot-1 archive
print("[test] re-archive shot-1...", flush=True)
r = s.post(f"{BASE}/projects/{PROJECT_ID}/shots/shot-1/archive",
           params={"scene_id": "scene-1"}, timeout=120, proxies={"http":None,"https":None})
print(f"[test] archive HTTP {r.status_code}", flush=True)
print(r.text[:500], flush=True)

# 2. 跑 render-queue shot-1
print("[test] render-queue shot-1...", flush=True)
r = s.post(f"{BASE}/projects/{PROJECT_ID}/render-queue",
           json={"shotIds": ["shot-1"], "samples": 16, "device": "GPU", "fps": 24},
           timeout=600, proxies={"http":None,"https":None})
print(f"[test] render HTTP {r.status_code}", flush=True)
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:2000], flush=True)
