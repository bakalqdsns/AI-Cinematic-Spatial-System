"""Continue the smoke test from the saved Z-Image still."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.comfyui_client import generate_minimax_video

OUT = ROOT / "test_outputs" / "comfy_smoke"
PNG = OUT / "zimage.png"
VIDEO_PROMPT = (
    "The woman in <Picture 1> takes two slow steps forward and smiles. "
    "Camera stays still. Keep her face, hair, and white-and-red dress unchanged."
)


async def main() -> None:
    png = PNG.read_bytes()
    print(f"minimax start bytes={len(png)}", flush=True)
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
