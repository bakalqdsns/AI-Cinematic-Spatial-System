"""
E2E: 自动三视图 pipeline.

流程：
  1. 解析纸境剧本 → 拿到 1 个角色 (林知夏)
  2. 调 auto_generate_three_views_for_project（fire-and-forget 同步等待版本）
  3. 验证：progress 表里该角色 status='done'，asset 含 reference_image +
     three_view_images{front, side, back} 都是 base64 PNG

测试用 mock image_generator 让 SDXL 不真的跑（生成一张 64x64 测试 PNG），
验证整条链路：LLM visual_prompt → 三视图 → project_store 持久化 → progress 更新。
"""
import asyncio
import base64
import json
import sys
from unittest.mock import patch, MagicMock
from PIL import Image
import io

sys.path.insert(0, r"F:\AICinematicSpatialSystem\backend")

from app.services.script_parser import Character
from app.services.auto_three_view import (
    auto_generate_three_views_for_project,
    get_progress,
)


# ── Mock helpers ────────────────────────────────────────────────────────────────


def _make_test_png(color=(128, 64, 200)) -> str:
    """Generate a 64x64 solid-colour PNG, return as base64."""
    img = Image.new("RGB", (64, 64), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── Mock helpers ────────────────────────────────────────────────────────────────

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
    print("E2E: auto_generate_three_views_for_project")
    print("=" * 70)

    # 1) Construct characters directly (skip LLM parse for unit-test isolation).
    chars = [
        Character(
            id="char-1",
            name="林知夏",
            gender="female",
            age="17",
            personality="敏感、警觉的学生",
            visual_prompt="young woman, school uniform, short hair, anime style",
        ),
        Character(
            id="char-2",
            name="陈老师",
            gender="male",
            age="45",
            personality="严肃的老师",
            visual_prompt="middle-aged man, glasses, formal wear, anime style",
        ),
    ]
    print(f"\n[setup] chars={len(chars)}:")
    for c in chars:
        print(f"  - {c.id} {c.name} {c.gender} {c.age}")

    project_id = "test_proj_e2e_001"

    # 2) Patch image generator so SDXL isn't really invoked.
    mock_gen = _MockGenerator()

    with patch("app.services.image_generator.get_image_generator", return_value=mock_gen), \
         patch("app.services.local_llm.get_llm_client") as mock_llm:
        # Provide a dummy LLM client in case visual_prompt is empty for some
        # character. (Our test characters already have visual_prompt set.)
        async_client = MagicMock()

        async def _mock_chat(messages, **kwargs):
            sys_msg = (messages[0]["content"] if messages else "").lower()
            if "metadata" in sys_msg or "logline" in sys_msg:
                return json.dumps({"title": "Paper World", "genre": "fantasy", "logline": "L"})
            return "young woman, anime style, character sheet"

        async_client.chat = _mock_chat
        mock_llm.return_value = async_client

        # Also patch project_store.save_character_asset so we don't touch disk.
        async def _mock_save(project_id, character_id, asset_type=None, file_data=None, extension="json", payload=None):
            payload = payload or asset_type
            print(f"[mock_save] project={project_id} char={character_id} "
                  f"asset_keys={list((payload or {}).keys())} "
                  f"views={list((payload.get('three_view_images') or {}).keys()) if payload else []}")
            return {"success": True, "url": f"<mock>/{character_id}_asset.json"}

        with patch("app.services.project_store.save_character_asset", side_effect=_mock_save):
            # 3) Run the auto-batch worker and await it.
            from app.services.script_parser import ScriptLanguage
            await auto_generate_three_views_for_project(
                project_id=project_id,
                characters=chars,
                genre="fantasy",
                language=ScriptLanguage.CHINESE,
            )

    # 4) Verify progress table
    progress = get_progress(project_id)
    print(f"\n[progress] project={project_id}:")
    for cid, entry in progress.items():
        print(f"  - {cid} {entry['name']:8s} status={entry['status']:8s} "
              f"elapsed={(entry.get('finished_at', 0) - entry.get('started_at', 0)):.2f}s "
              f"err={entry.get('error')}")

    # ── Assertions ──────────────────────────────────────────────────────────────
    errors = []
    if not progress:
        errors.append("progress is empty")
    for cid in [c.id for c in chars]:
        entry = progress.get(cid)
        if not entry:
            errors.append(f"{cid}: no progress entry")
            continue
        if entry["status"] != "done":
            errors.append(f"{cid}: status={entry['status']!r}, expected 'done'")
        if not entry.get("visual_prompt"):
            errors.append(f"{cid}: visual_prompt missing")
        asset = entry.get("asset")
        if not asset:
            errors.append(f"{cid}: asset missing")
        else:
            tvi = asset.get("three_view_images") or {}
            for view in ("front", "side", "back"):
                if not tvi.get(view):
                    errors.append(f"{cid}: three_view_images.{view} missing")
                else:
                    # Verify it's valid base64 PNG
                    try:
                        decoded = base64.b64decode(tvi[view])
                        img = Image.open(io.BytesIO(decoded))
                        if img.format != "PNG":
                            errors.append(f"{cid}: {view} image not PNG, got {img.format}")
                    except Exception as e:
                        errors.append(f"{cid}: {view} not valid base64 PNG: {e}")

    print("\n" + "=" * 70)
    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print(f"[OK] auto-batch generated 3-view turnaround for {len(chars)} character(s)")
    print(f"     each produced {len(chars)*3} PNGs via mock generator")


if __name__ == "__main__":
    asyncio.run(main())