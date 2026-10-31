"""Scene image -> depth layers -> Blender render, with a character plane."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import cv2
import httpx

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test_outputs" / "scene_chain"
GREEN = ROOT / ".cache" / "comfy" / "minimax_689a1ccd.mp4"
TINY = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01"
    b"\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def plant_character_frames(project_id: str) -> int:
    dest = ROOT / ".workspace" / "projects" / project_id / "motions" / "hero" / "steps"
    dest.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(GREEN))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        raise SystemExit("character video has no frames")
    want = 24
    step = max(1, total // want)
    written = 0
    index = 0
    while written < want:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            break
        cv2.imwrite(str(dest / f"frame_{written + 1:04d}.png"), frame)
        written += 1
        index += step
    cap.release()
    return written


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(1800.0, connect=30.0)
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        created = client.post(
            f"{BASE}/api/aicss/projects/json",
            json={"shotId": "scene_chain", "imageBase64": base64.b64encode(TINY).decode("ascii")},
        )
        created.raise_for_status()
        project_id = created.json()["projectId"]
        print("PROJECT", project_id, flush=True)

        scene = client.post(
            f"{BASE}/api/aicss/v2/scripts/scenes/generate-asset",
            json={
                "scene_id": "scene-1",
                "location": "ancient stone courtyard",
                "time": "Day",
                "atmosphere": "quiet, open air",
                "visual_prompt": (
                    "ancient stone courtyard with wooden pillars, paper lanterns, "
                    "and a cloudy sky, empty of people"
                ),
                "project_id": project_id,
            },
        )
        scene.raise_for_status()
        keys = list((scene.json().get("keyframe_images") or {}).keys())
        print("SCENE_OK", keys, flush=True)

        shot = client.post(
            f"{BASE}/api/aicss/v2/projects/{project_id}/shots",
            json={"shotId": "shot-1", "description": "courtyard with character", "sceneType": "outdoor"},
        )
        shot.raise_for_status()
        frames = plant_character_frames(project_id)
        print("CHARACTER_FRAMES", frames, flush=True)

        archive = client.post(
            f"{BASE}/api/aicss/v2/projects/{project_id}/shots/shot-1/archive",
            params={"scene_id": "scene-1", "lighting_preset": "warm_interior"},
        )
        archive.raise_for_status()
        meta = archive.json()
        print(
            "ARCHIVE",
            json.dumps({k: meta.get(k) for k in ("fileName", "layerCount", "meshCount", "fileCount")}, ensure_ascii=False),
            flush=True,
        )

        rendered = client.post(
            f"{BASE}/api/aicss/v2/projects/{project_id}/render-queue",
            json={
                "shotIds": ["shot-1"],
                "samples": 8,
                "resolution": [960, 540],
                "device": "GPU",
                "fps": 24,
                "lightingPreset": "warm_interior",
            },
        )
        rendered.raise_for_status()
        print("RENDER", json.dumps(rendered.json(), ensure_ascii=False)[:2000], flush=True)


if __name__ == "__main__":
    main()
