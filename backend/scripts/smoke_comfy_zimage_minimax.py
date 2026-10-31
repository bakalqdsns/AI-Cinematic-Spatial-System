"""Smoke test: Z-Image still, then MiniMax video using that still as reference."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.comfyui_client import generate_minimax_video, generate_zimage_png

OUT = ROOT / "test_outputs" / "comfy_smoke"
PROMPT = (
    "full body portrait of a young woman with long white hair, "
    "white and red fantasy dress, standing, plain soft studio background, sharp face"
)
VIDEO_PROMPT = (
    "The woman in the reference image takes two slow steps forward and smiles. "
    "Camera stays still. Keep her face, hair, and costume unchanged."
)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("zimage start", flush=True)
    png = await generate_zimage_png(PROMPT, width=768, height=1024, seed=42)
    image_path = OUT / "zimage.png"
    image_path.write_bytes(png)
    print(f"IMAGE_OK {image_path} bytes={len(png)}", flush=True)

    print("minimax start", flush=True)
    video = await generate_minimax_video(
        VIDEO_PROMPT,
        duration_seconds=5,
        seed=42,
        reference_png=png,
    )
    video_path = OUT / "minimax.mp4"
    video_path.write_bytes(video)
    print(f"VIDEO_OK {video_path} bytes={len(video)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
