# -*- coding: utf-8 -*-
"""单 shot motion 端到端测试：读角色 front.png -> POST /scripts/motion/generate"""
import sys, base64, json, urllib.request, urllib.error, os, io
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8001
PROJECT_ID = "20260927_055614_旧相册"
WORKSPACE = Path("F:/AICinematicSpatialSystem/backend/.workspace/projects") / PROJECT_ID

# 选 shot-1 x char-1（李明）
SHOT_ID = "shot-1"
CHAR_ID = "char-1"
CHAR_NAME = "李明"
ACTION_PROMPT = "李明走进咖啡馆，推门而入，环顾四周"

# 关掉代理
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

# 找角色 front.png
front_png = None
char_dir = WORKSPACE / "characters" / CHAR_NAME / "three_view"
for cand in [char_dir / "front.png", char_dir / "reference_image.png"]:
    if cand.exists():
        front_png = cand
        break
if front_png is None:
    # fallback: 找任何 front.png
    for p in (WORKSPACE / "characters").rglob("front.png"):
        front_png = p
        break
print(f"[test] using start image: {front_png}")
assert front_png and front_png.exists(), "no front.png found"

# resize to 480 wide (DashScope wan2.5-i2v 大图会卡住)
from PIL import Image
img = Image.open(front_png)
w, h = img.size
new_w = 480
new_h = int(h * new_w / w)
img = img.resize((new_w, new_h), Image.LANCZOS)
buf = io.BytesIO()
img.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode("ascii")
print(f"[test] resized {w}x{h} -> {new_w}x{new_h}, base64 len={len(b64)}")

body = {
    "shot_id": SHOT_ID,
    "character_id": CHAR_ID,
    "character_name": CHAR_NAME,
    "action_prompt": ACTION_PROMPT,
    "start_image": b64,
    "duration_seconds": 5.0,
    "video_provider": "dashscope",
    "project_id": PROJECT_ID,
}
import requests
data = json.dumps(body).encode("utf-8")
url = f"http://{HOST}:{PORT}/api/aicss/v2/scripts/motion/generate"
print(f"[test] POST {url}", flush=True)
sess = requests.Session()
sess.trust_env = False  # 不读系统代理
resp = sess.post(url, data=data, headers={"Content-Type":"application/json"}, timeout=600, proxies={"http":None,"https":None})
print(f"[test] HTTP {resp.status_code}", flush=True)
print(resp.text[:2000], flush=True)
