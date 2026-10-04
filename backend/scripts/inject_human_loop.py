# -*- coding: utf-8 -*-
"""把绿幕视频转成 24 帧 PNG 序列 + chroma key 抠绿，注入 motions 目录。
同时构造新项目的 manifest.json + pipeline_state.json，然后调 archive→render→compose。"""
import os, json, subprocess, shutil
from pathlib import Path
import numpy as np
import cv2

PROJ = Path(r"F:\AICinematicSpatialSystem\backend\.workspace\projects\20261004_人机协同测试")
VIDEO = Path(r"F:\AICinematicSpatialSystem\backend\scripts\inputs\shot3_greenscreen.mp4")
FFMPEG = Path(r"F:\AICinematicSpatialSystem\backend\bin\ffmpeg.exe")
MOTION_DIR = PROJ / "motions" / "liming" / "shot3_action"
MOTION_DIR.mkdir(parents=True, exist_ok=True)

# 1. ffmpeg 抽帧（5秒@24fps ≈ 122 帧，全部抽取，让动作 1:1 对应原始 5 秒）
print("[1] extracting frames...", flush=True)
for old in MOTION_DIR.glob("frame_*.png"):
    old.unlink()
# 抽成 24fps 帧序列（不加 -frames:v，抽全部帧 = 源视频时长 × 24fps）
raw_dir = MOTION_DIR / "_raw"
raw_dir.mkdir(exist_ok=True)
for old in raw_dir.glob("*.png"):
    old.unlink()
r = subprocess.run([str(FFMPEG), "-y", "-i", str(VIDEO), "-vf", "fps=24",
                    str(raw_dir / "f_%04d.png")],
                   capture_output=True, text=True, timeout=120)
print(f"   ffmpeg exit={r.returncode}", flush=True)
if r.returncode != 0:
    print(r.stderr[-500:], flush=True)
    raise SystemExit(1)

raw_frames = sorted(raw_dir.glob("*.png"))
print(f"   extracted {len(raw_frames)} raw frames", flush=True)

# 2. chroma key 抠绿 → RGBA（用 HSV 色相范围，比 RGB 欧氏距离稳）
#    先抠所有帧算联合 bbox，再裁剪居中，让角色填充画面而非只占左上角一小条。
print("[2] chroma key (HSV) + auto-crop...", flush=True)
def _imread_unicode(p):
    with open(p, "rb") as f:
        data = f.read()
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)
def _imwrite_unicode(p, bgra):
    ok, buf = cv2.imencode(".png", bgra)
    with open(p, "wb") as f:
        f.write(buf.tobytes())
# 绿幕常见色相 H=60（OpenCV 0-180 对应 0-360°，绿=60°→H=30）；放宽到 H∈[25,90]
GREEN_LO = np.array([25, 40, 40], np.uint8)   # H,S,V 下界
GREEN_HI = np.array([90, 255, 255], np.uint8) # H,S,V 上界

# 第一遍：抠绿，收集所有帧的 alpha mask
alphas = []
for i, fp in enumerate(raw_frames):
    img = _imread_unicode(str(fp))  # BGR
    if img is None:
        print(f"   skip {fp.name}: read failed", flush=True)
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, GREEN_LO, GREEN_HI)  # 255=绿幕, 0=前景
    mask = cv2.dilate(mask, np.ones((3,3), np.uint8), iterations=1)
    mask = cv2.GaussianBlur(mask, (5,5), 0)
    alpha = 255 - mask  # 前景=255, 绿幕=0
    alphas.append((i, img, alpha))

h0, w0 = alphas[0][1].shape[:2] if alphas else (720, 1280)
OUT_W, OUT_H = w0, h0  # 保持原尺寸 1280x720

# 用每帧各自的 bbox 裁剪居中，让每帧角色都居中填充画面
for i, img, alpha in alphas:
    ys, xs = np.where(alpha > 128)
    if len(xs) == 0:
        # 无前景，直接透明
        bgra = np.zeros((OUT_H, OUT_W, 4), np.uint8)
        out = MOTION_DIR / f"frame_{i:03d}.png"
        _imwrite_unicode(str(out), bgra)
        print(f"   frame_{i:03d}.png no fg, blank", flush=True)
        continue
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = max(1, x1 - x0); bh = max(1, y1 - y0)
    # padding 10% 让角色不贴边
    pad = int(max(bw, bh) * 0.10)
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(w0-1, x1 + pad); y1 = min(h0-1, y1 + pad)
    bw = max(1, x1 - x0); bh = max(1, y1 - y0)
    # 裁剪
    img_crop = img[y0:y1+1, x0:x1+1]
    a_crop = alpha[y0:y1+1, x0:x1+1]
    # contain 模式缩放到填充画布（角色完整，留白透明）
    scale = min(OUT_W / bw, OUT_H / bh)
    new_w = int(round(bw * scale)); new_h = int(round(bh * scale))
    img_scaled = cv2.resize(img_crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    a_scaled = cv2.resize(a_crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
    # 居中放到画布
    canvas_img = np.zeros((OUT_H, OUT_W, 3), np.uint8)
    canvas_a = np.zeros((OUT_H, OUT_W), np.uint8)
    ox = (OUT_W - new_w) // 2; oy = (OUT_H - new_h) // 2
    canvas_img[oy:oy+new_h, ox:ox+new_w] = img_scaled
    canvas_a[oy:oy+new_h, ox:ox+new_w] = a_scaled
    bgra = cv2.cvtColor(canvas_img, cv2.COLOR_BGR2BGRA)
    bgra[:,:,3] = canvas_a
    out = MOTION_DIR / f"frame_{i:03d}.png"
    _imwrite_unicode(str(out), bgra)
    ratio = float((canvas_a > 128).sum()) / canvas_a.size
    print(f"   frame_{i:03d}.png bbox {bw}x{bh} scale={scale:.2f} -> {new_w}x{new_h} fg={ratio:.1%}", flush=True)

# 清理 raw
shutil.rmtree(raw_dir, ignore_errors=True)
n_frames = len(list(MOTION_DIR.glob("frame_*.png")))
print(f"[2] done: {n_frames} RGBA frames", flush=True)

# 3. 写 _meta.json
(MOTION_DIR / "_meta.json").write_text(
    json.dumps({"fps": 24, "frame_count": n_frames, "greenscreen": True}), encoding="utf-8")
print("[3] _meta.json written", flush=True)
