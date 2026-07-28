"""
E2E: 自动场景资产 pipeline.

流程：
  1. 构造 2 个场景 (纸境-夜 / 校园-日)
  2. 调 auto_generate_scene_assets_for_project（同步等待版本）
  3. 验证：progress 表里 status='done'，asset 含 wide/closeup/mood 三张 PNG

测试用 mock image_generator 让 SDXL 不真的跑（生成 64x64 测试 PNG），
验证整条链路：LLM visual_prompt → 3 keyframes → project_store 持久化 → progress 更新。
"""
import asyncio
import base64
import io
import json
import sys
from unittest.mock import patch, MagicMock
from PIL import Image

sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend")

from app.services.script_parser import Scene
from app.services.auto_scene_view import (
    auto_generate_scene_assets_for_project,
    get_progress,
)


class _MockGenerator:
    """Stand-in for LocalImageGenerator that produces fast PNGs."""

    def __init__(self):
        self.counter = 0
        self.colors = [(220, 80, 80), (80, 180, 220), (80, 220, 120)]

    def generate(self, prompt, seed=None, **kwargs):
        img = Image.new("RGB", (64, 64), self.colors[self.counter % 3])
        self.counter += 1
        return img

    def generate_with_image(self, prompt, reference_image, strength=0.7, **kwargs):
        img = Image.new("RGB", (64, 64), self.colors[self.counter % 3])
        self.counter += 1
        return img

    def pil_to_base64(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")


async def main() -> None:
    print("=" * 70)
    print("E2E: auto_generate_scene_assets_for_project")
    print("=" * 70)

    # 1) Construct scenes directly (skip LLM parse for unit-test isolation).
    scenes = [
        Scene(
            id="scene-1",
            location="纸境",
            time="Night",
            atmosphere="魔幻",
            visual_prompt="a vast paper-craft world, blue sky, cardboard clouds",
        ),
        Scene(
            id="scene-2",
            location="教室",
            time="Day",
            atmosphere="温馨",
            visual_prompt="a high-school classroom, sunny afternoon",
        ),
    ]
    print(f"\n[setup] scenes={len(scenes)}:")
    for s in scenes:
        print(f"  - {s.id} {s.location} {s.time} {s.atmosphere}")

    project_id = "test_proj_scene_e2e_001"

    # 2) Patch image generator so SDXL isn't really invoked.
    mock_gen = _MockGenerator()

    with patch("app.services.image_generator.get_image_generator", return_value=mock_gen), \
         patch("app.services.local_llm.get_llm_client") as mock_llm:
        async_client = MagicMock()

        async def _mock_chat(messages, **kwargs):
            sys_msg = (messages[0]["content"] if messages else "").lower()
            if "metadata" in sys_msg or "logline" in sys_msg:
                return json.dumps({"title": "Paper World", "genre": "fantasy", "logline": "L"})
            return "paper-craft world, cinematic wide shot, anime background art"

        async_client.chat = _mock_chat
        mock_llm.return_value = async_client

        async def _mock_save(project_id, scene_id, payload=None, **kwargs):
            p = payload or kwargs.get("asset_type")
            print(f"[mock_save] project={project_id} scene={scene_id} "
                  f"keys={list((p or {}).keys())} "
                  f"views={list((p.get('keyframe_images') or {}).keys()) if p else []}")
            return {"success": True, "url": f"<mock>/{scene_id}_asset.json"}

        with patch("app.services.project_store.save_scene_asset", side_effect=_mock_save):
            from app.services.script_parser import ScriptLanguage
            await auto_generate_scene_assets_for_project(
                project_id=project_id,
                scenes=scenes,
                genre="fantasy",
                language=ScriptLanguage.CHINESE,
            )

    # 3) Verify progress table
    progress = get_progress(project_id)
    print(f"\n[progress] project={project_id}:")
    for sid, entry in progress.items():
        elapsed = (entry.get("finished_at", 0) - entry.get("started_at", 0))
        print(f"  - {sid} {entry['name']:8s} status={entry['status']:8s} "
              f"elapsed={elapsed:.2f}s err={entry.get('error')}")

    # ── Assertions ──────────────────────────────────────────────────────────────
    errors = []
    if not progress:
        errors.append("progress is empty")
    for s in scenes:
        entry = progress.get(s.id)
        if not entry:
            errors.append(f"{s.id}: no progress entry")
            continue
        if entry["status"] != "done":
            errors.append(f"{s.id}: status={entry['status']!r}, expected 'done'")
        if not entry.get("visual_prompt"):
            errors.append(f"{s.id}: visual_prompt missing")
        asset = entry.get("asset")
        if not asset:
            errors.append(f"{s.id}: asset missing")
        else:
            kf = asset.get("keyframe_images") or {}
            for view in ("wide", "closeup", "mood"):
                if not kf.get(view):
                    errors.append(f"{s.id}: keyframe_images.{view} missing")
                else:
                    try:
                        decoded = base64.b64decode(kf[view])
                        img = Image.open(io.BytesIO(decoded))
                        if img.format != "PNG":
                            errors.append(f"{s.id}: {view} not PNG, got {img.format}")
                    except Exception as e:
                        errors.append(f"{s.id}: {view} not valid base64 PNG: {e}")

    print("\n" + "=" * 70)
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"[OK] auto-batch generated 3-view keyframes for {len(scenes)} scene(s)")
    print(f"     each produced {len(scenes)*3} PNGs via mock generator")


if __name__ == "__main__":
    asyncio.run(main())