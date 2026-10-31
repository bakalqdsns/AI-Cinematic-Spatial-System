"""Drive the AICSS HTTP API: ComfyUI still, then ComfyUI motion video."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "test_outputs" / "comfy_system"
PROMPT = (
    "full body portrait of a young woman with long white hair, "
    "white and red fantasy dress, standing, plain soft studio background, sharp face"
)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(900.0, connect=30.0)
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        settings = client.post(
            f"{BASE}/api/aicss/settings",
            json={
                "image_mode": "local",
                "local_image_backend": "comfyui",
                "video_mode": "local",
                "video_provider": "comfyui",
                "comfyui_base_url": "http://127.0.0.1:8188",
            },
        )
        settings.raise_for_status()
        body = settings.json()
        print(
            "settings",
            body.get("image_mode"),
            body.get("local_image_backend"),
            body.get("video_mode"),
            body.get("video_provider"),
            body.get("comfyui_base_url"),
            flush=True,
        )

        image = client.post(
            f"{BASE}/api/aicss/v2/scripts/characters/generate-variation",
            json={
                "character_id": "char_comfy",
                "variation_prompt": PROMPT,
            },
        )
        image.raise_for_status()
        image_body = image.json()
        raw = image_body.get("image") or ""
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        if not raw:
            raise SystemExit(f"IMAGE_EMPTY {json.dumps({k: image_body.get(k) for k in image_body if k != 'image'})}")
        png = base64.b64decode(raw)
        image_path = OUT / "variation.png"
        image_path.write_bytes(png)
        print(f"IMAGE_OK {image_path} bytes={len(png)}", flush=True)

        motion = client.post(
            f"{BASE}/api/aicss/v2/scripts/motion/generate",
            json={
                "shot_id": "shot-1",
                "character_id": "char_comfy",
                "character_name": "白发角色",
                "action_prompt": "The woman in the reference image takes two slow steps forward and smiles. Camera stays still.",
                "start_image": raw,
                "duration_seconds": 5,
                "video_provider": "comfyui",
                "greenscreen": False,
                "feather_edges": False,
            },
        )
        motion.raise_for_status()
        motion_body = motion.json()
        summary = {k: motion_body.get(k) for k in ("status", "video_path", "frame_count", "error") if k in motion_body or True}
        print("MOTION", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
