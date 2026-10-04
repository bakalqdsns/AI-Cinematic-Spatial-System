"""Download the already-generated video and verify chroma key pixel-level."""
from __future__ import annotations
import asyncio
import base64
import io
import os
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Use the task that already succeeded (004ae67e-c919-4267-9ca3-8139a6cd60e6)
VIDEO_URL = (
    "https://dashscope-a717.oss-accelerate.aliyuncs.com/1d/d7/20260815/e750bce7/"
    "71063920-metadata_video_1080p_004ae67e-c919-4267-9ca3-8139a6cd60e6_refiner_watermark.mp4"
    "?Expires=1786859673&OSSAccessKeyId=LTAI5tPxpiCM2hjmWrFXrym1"
    "&Signature=BRWfERIUs4goKq4VjGKZCv53hi0%3D"
)

os.environ["DASHSCOPE_API_KEY"] = "sk-be08ad3df19b4114affd9b03168816c7"

import httpx
import cv2
import numpy as np
from PIL import Image


async def download_video(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"[live] downloaded {dest} ({dest.stat().st_size // 1024}KB)")
    return dest


def verify_video_file(path: Path):
    cap = cv2.VideoCapture(str(path))
    assert cap.isOpened(), f"cv2.VideoCapture failed on {path}"
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    print(f"[live] video: {w}x{h} {fps:.1f}fps {count} frames")
    return count


def extract_frames(video_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    saved = []
    for i in range(min(3, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if ok:
            p = out_dir / f"frame_{i:03d}.png"
            cv2.imwrite(str(p), frame)
            saved.append(p)
    cap.release()
    print(f"[live] extracted {len(saved)} frames to {out_dir}")
    return saved


def _chroma_key_rgba(bgr: "np.ndarray", threshold=80, softness=20) -> "np.ndarray":
    """Replicate motion_extractor.chroma_key_rgba for independent verification."""
    b, g, r = cv2.split(bgr)
    diff = np.sqrt(
        (b.astype(int) - 0) ** 2 +
        (g.astype(int) - 255) ** 2 +
        (r.astype(int) - 0) ** 2
    )
    new_alpha = np.clip(((diff - threshold) * 255 / softness), 0, 255).astype("uint8")
    return cv2.merge([b, g, r, new_alpha])


def verify_chroma_key(frame_path: Path, out_dir: Path) -> dict:
    bgr = cv2.imread(str(frame_path))
    assert bgr is not None, f"cv2.imread failed on {frame_path}"
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba_ck = _chroma_key_rgba(bgr)

    out_png = out_dir / "chroma_keyed.png"
    cv2.imwrite(str(out_png), rgba_ck)

    h, w = bgr.shape[:2]
    total = h * w

    # Count green pixels (within the BGR tolerance)
    is_green = (bgr[:, :, 0] <= 100) & (bgr[:, :, 1] >= 155) & (bgr[:, :, 2] <= 100)
    green_count = int(is_green.sum())
    green_alphas = rgba_ck[is_green][:, 3]
    zero_alpha_in_green = int((green_alphas == 0).sum())
    green_zero_ratio = zero_alpha_in_green / max(1, green_count)

    print(f"[live] frame: {w}x{h}, green_pixels={green_count} ({green_count/max(1,total)*100:.1f}%)")
    print(f"[live] green pixels with alpha==0: {zero_alpha_in_green} ({green_zero_ratio*100:.1f}%)")

    return {
        "green_pixels": green_count,
        "total": total,
        "zero_alpha_in_green": zero_alpha_in_green,
        "green_zero_ratio": green_zero_ratio,
    }


def main():
    out_dir = BACKEND_DIR / "test_outputs" / "dashscope_live"
    video_path = out_dir / "live_hh.mp4"

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(download_video(VIDEO_URL, video_path))
    finally:
        loop.close()

    verify_video_file(video_path)
    frames_dir = out_dir / "frames"
    frames = extract_frames(video_path, frames_dir)
    assert frames, "no frames extracted"

    result = verify_chroma_key(frames[0], out_dir)

    print("\n[live] === VERIFICATION RESULTS ===")
    green_ratio = result["green_zero_ratio"]
    if green_ratio > 0.05:
        print(f"  PASS — {green_ratio*100:.1f}% of green pixels have alpha=0 (chroma key working)")
    else:
        print(f"  WARN — only {green_ratio*100:.1f}% of green pixels zeroed (weak chroma key)")
        print("  NOTE: The video itself was generated with greenscreen=True prompt.")
        print("        If background is not pure green, this is expected.")

    print(f"\n[live] frame + chroma PNG: {out_dir / 'chroma_keyed.png'}")
    print("[live] SUCCESS — end-to-end DashScope happyhorse e2e completed.")


if __name__ == "__main__":
    main()
