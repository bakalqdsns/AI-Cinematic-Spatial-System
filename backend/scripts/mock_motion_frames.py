# -*- coding: utf-8 -*-
"""构造 mock motion 帧序列：把角色 front.png 复制成 24 帧静态 PNG，
让 shot_archiver 能扫描到 frame_*.png，从而跑通 archive→render→compose。"""
import shutil
from pathlib import Path
from PIL import Image

PROJECT = Path("F:/AICinematicSpatialSystem/backend/.workspace/projects/20260927_055614_旧相册")
MOTIONS = PROJECT / "motions"

for char_name in ["李明", "张华"]:
    src = PROJECT / "characters" / char_name / "three_view" / "front.png"
    if not src.exists():
        print(f"[mock] skip {char_name}: {src} missing")
        continue
    dst_dir = MOTIONS / char_name / "mock_action"
    dst_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(src)
    # 写 24 帧（1 秒 @ 24fps）
    for i in range(24):
        frame = dst_dir / f"frame_{i:03d}.png"
        img.save(frame, "PNG")
    # 写 _meta.json
    (dst_dir / "_meta.json").write_text('{"fps": 24, "frame_count": 24, "note": "mock static frames for pipeline test"}', encoding="utf-8")
    print(f"[mock] {char_name}: 24 frames -> {dst_dir}")

print("[mock] done")
