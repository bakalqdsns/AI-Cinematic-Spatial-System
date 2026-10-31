"""Re-run only the motion API so the ComfyUI path emits a green-screen video."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
PNG = Path(__file__).resolve().parents[1] / "test_outputs" / "comfy_system" / "variation.png"


def main() -> None:
    raw = base64.b64encode(PNG.read_bytes()).decode("ascii")
    with httpx.Client(timeout=httpx.Timeout(900.0, connect=30.0), trust_env=False) as client:
        motion = client.post(
            f"{BASE}/api/aicss/v2/scripts/motion/generate",
            json={
                "shot_id": "shot-green",
                "character_id": "char_comfy",
                "character_name": "白发角色",
                "action_prompt": "takes two slow steps forward and smiles",
                "start_image": raw,
                "duration_seconds": 5,
                "video_provider": "comfyui",
                "greenscreen": False,
            },
        )
        motion.raise_for_status()
        body = motion.json()
        print(
            "MOTION",
            json.dumps(
                {k: body.get(k) for k in ("status", "video_path", "frame_count")},
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
