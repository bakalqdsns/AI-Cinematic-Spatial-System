# -*- coding: utf-8 -*-
"""调 render-queue 看返回内容"""
import os, json, requests
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)
PROJECT_ID = "20260927_055614_旧相册"
url = f"http://127.0.0.1:8001/api/aicss/v2/projects/{PROJECT_ID}/render-queue"
body = {"shotIds": [f"shot-{i}" for i in range(1,15)], "samples": 16, "device": "GPU", "fps": 24}
s = requests.Session(); s.trust_env = False
r = s.post(url, json=body, timeout=300, proxies={"http":None,"https":None})
print("HTTP", r.status_code)
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:3000])
