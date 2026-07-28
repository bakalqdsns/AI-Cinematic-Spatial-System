"""
Scene Generator Service
========================

Mirrors character_generator but produces a 3-shot reference set per scene:
  - wide     : establishing shot, full location, sets time + geography
  - closeup  : detail of the most striking element (sign / object / texture)
  - mood     : atmosphere / ambient mood board (no subject, just light + tone)

The first shot (wide) is generated via txt2img and acts as the visual anchor.
The other two reuse it via img2img at higher strength so colour palette and
art style stay consistent across the three views.

Mode routing:
  - image_mode == "cloud" → DashScope ImageSynthesis API (no img2img fallback)
  - image_mode == "local"  → local Diffusers (Z-Image / SDXL)
  - model_mode  == "cloud" → DashScope LLM for prompt generation
  - model_mode  == "local" → local llama.cpp LLM
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from .script_parser import Scene, ScriptLanguage


SCENE_VIEWS = ("wide", "closeup", "mood")


GENERATE_SCENE_VISUAL_PROMPT_CHINESE = """你是一个专业的视觉提示词生成师。请为以下场景生成英文视觉描述提示词。

要求：
1. 输出纯英文描述，逗号分隔，最多 60 词
2. 描述场景的空间布局，光线、材质、配色、时代感
3. 使用电影/动画/概念美术的视觉语言
4. 不要解释，只输出提示词

示例：
a vast paper-craft world, hand-cut cardboard clouds, blue craft-paper sky, warm diffuse lighting, soft shadows, anime background art, high detail, cinematic composition, empty no people"""

GENERATE_SCENE_VISUAL_PROMPT_ENGLISH = """You are a professional visual prompt engineer. Generate English visual description prompts for the following scene.

Requirements:
1. Pure English, comma-separated, max 60 words
2. Describe the space: layout, lighting, materials, palette, era
3. Use cinematic / anime / concept-art visual language
4. Output only the prompt, no explanation"""

GENERATE_SCENE_VISUAL_PROMPT_JAPANESE = """あなたはプロフェッショナルなビジュアルプロンプトエンジニアです。以下のシーンの英語のビジュアル説明プロンプトを生成してください。

要件：
1. 純粋な英語、カンマ区切り、最大60語
2. 空間のレイアウト，光、素材、パレット、時代感を描述
3. 映画/アニメ/コンセプトアートのビジュアル言語を使用"""


@dataclass
class SceneAsset:
    scene_id: str
    visual_prompt: str
    keyframe_images: dict[str, Optional[str]] = field(default_factory=dict)
    # keys: wide / closeup / mood — values: base64 PNG or None
    variations: list["SceneVariation"] = field(default_factory=list)


@dataclass
class SceneVariation:
    id: str
    name: str
    visual_prompt: str
    image: Optional[str] = None  # base64


# ── Settings helpers ────────────────────────────────────────────────────────────

def _get_image_mode() -> str:
    try:
        from app.config import settings
        return settings.image_mode
    except Exception:
        return "local"


def _get_model_mode() -> str:
    try:
        from app.config import settings
        return settings.model_mode
    except Exception:
        return "local"


# ── LLM: visual prompt ──────────────────────────────────────────────────────────

async def generate_scene_visual_prompt(
    scene: Scene,
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> str:
    """
    Generate an English visual art prompt describing the scene as a location
    (no characters, no action).

    Routes through settings.model_mode: cloud → DashScope, local → llama.cpp.
    """
    prompts = {
        ScriptLanguage.CHINESE: GENERATE_SCENE_VISUAL_PROMPT_CHINESE,
        ScriptLanguage.ENGLISH: GENERATE_SCENE_VISUAL_PROMPT_ENGLISH,
        ScriptLanguage.JAPANESE: GENERATE_SCENE_VISUAL_PROMPT_JAPANESE,
    }
    system_prompt = prompts[language]

    time_text = {
        "Day": "daytime", "Night": "night", "Dawn": "dawn",
        "Dusk": "dusk", "Morning": "morning", "Evening": "evening",
    }.get(scene.time, scene.time.lower())

    user_text = (
        f"场景地点: {scene.location}\n"
        f"时间: {time_text}\n"
        f"氛围: {scene.atmosphere}\n"
        f"题材风格: {genre}\n\n"
        f"请生成视觉描述提示词："
    )

    model_mode = _get_model_mode()

    if model_mode == "cloud":
        try:
            from app.services.dashscope_client import get_dashscope_client
            client = get_dashscope_client()
            content = await asyncio.to_thread(
                client.chat,
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": user_text}],
                temperature=0.3,
                max_tokens=256,
            )
            if content:
                return content.strip()
        except Exception as e:
            logger.warning("[scene_generator] DashScope LLM visual prompt failed: %s", e)
    else:
        try:
            from .local_llm import get_llm_client
            client = get_llm_client()
            content = await client.chat(
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": user_text}],
                temperature=0.3,
                max_tokens=256,
            )
            if content:
                return content.strip()
        except Exception as e:
            logger.warning("[scene_generator] Local LLM visual prompt failed: %s", e)

    # Fallback: deterministic prompt derived from scene metadata.
    return (
        f"{scene.location}, {time_text}, {scene.atmosphere}, "
        f"{genre} style, empty scene, no people, cinematic wide shot, "
        f"high detail, concept art background"
    )


# ── Image: 3-shot keyframe set ──────────────────────────────────────────────────

async def generate_scene_keyframes(
    scene: Scene,
    visual_prompt: Optional[str] = None,
    *,
    anchor_image: Optional[str] = None,
    seed: Optional[int] = None,
    max_retries: int = 2,
    size: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """
    Generate three keyframe images for a scene: wide / closeup / mood.

    Strategy:
      1. Generate a "wide" anchor image (txt2img) — establishing shot.
      2. Derive closeup + mood via img2img from the wide anchor for
         palette/style consistency.

    If ``anchor_image`` is provided (e.g. user uploaded a reference), step 1
    is skipped and we use the supplied image instead.
    """
    base_prompt = visual_prompt or scene.visual_prompt
    if not base_prompt:
        base_prompt = await generate_scene_visual_prompt(scene)

    results: dict[str, Optional[str]] = {"wide": None, "closeup": None, "mood": None}
    out_size = size or _default_scene_size()

    # ── Step 1: wide establishing shot ────────────────────────────────────────
    if anchor_image:
        anchor_b64 = anchor_image
        results["wide"] = anchor_b64
    else:
        wide_prompt = (
            f"{base_prompt}, wide establishing shot, full location visible, "
            f"cinematic composition, no people, no characters, empty scene, "
            f"concept art background, high detail, dramatic lighting"
        )
        anchor_b64 = await _generate_with_retry(
            wide_prompt, label=f"{scene.id}:wide", seed=seed, size=out_size,
        )
        results["wide"] = anchor_b64

    if not anchor_b64:
        logger.warning("[scene_generator] %s wide anchor failed; skipping derivations", scene.id)
        return results

    # ── Step 2: closeup detail via img2img ────────────────────────────────────
    closeup_prompt = (
        f"{base_prompt}, close-up detail, focus on a striking prop or texture, "
        f"shallow depth of field, same art style, same palette"
    )
    results["closeup"] = await _img2img_with_retry(
        closeup_prompt, anchor_b64, label=f"{scene.id}:closeup", strength=0.7,
    )

    # ── Step 3: mood / atmosphere via img2img ─────────────────────────────────
    mood_prompt = (
        f"{base_prompt}, atmospheric mood shot, ambient light and shadow, "
        f"silhouette only, empty foreground, focus on color and tone, "
        f"same art style, same palette"
    )
    results["mood"] = await _img2img_with_retry(
        mood_prompt, anchor_b64, label=f"{scene.id}:mood", strength=0.55,
    )

    return results


async def _generate_with_retry(
    prompt: str,
    *,
    label: str,
    seed: Optional[int] = None,
    max_retries: int = 2,
    size: Optional[str] = None,
) -> Optional[str]:
    last_exc = None
    image_mode = _get_image_mode()
    out_size = size or _default_scene_size()

    for attempt in range(max_retries + 1):
        try:
            if image_mode == "cloud":
                return await _generate_via_cloud(prompt, size=out_size)
            else:
                return await _generate_via_local(prompt, seed=seed, size=out_size)
        except Exception as e:
            last_exc = e
            logger.warning(
                "[scene_generator] %s attempt %d failed (mode=%s): %s",
                label, attempt + 1, image_mode, e,
            )
            if attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))

    logger.error("[scene_generator] %s exhausted retries: %s", label, last_exc)
    return None


async def _img2img_with_retry(
    prompt: str,
    anchor_b64: str,
    *,
    label: str,
    strength: float = 0.7,
    max_retries: int = 2,
) -> Optional[str]:
    last_exc = None
    image_mode = _get_image_mode()

    for attempt in range(max_retries + 1):
        try:
            if image_mode == "cloud":
                # DashScope doesn't natively support img2img — fall back to txt2img
                # with a stronger prompt so we don't block the whole cloud path.
                return await _generate_via_cloud(prompt)
            else:
                return await _generate_via_local_with_reference(prompt, anchor_b64, strength=strength)
        except Exception as e:
            last_exc = e
            logger.warning(
                "[scene_generator] %s attempt %d failed (mode=%s): %s",
                label, attempt + 1, image_mode, e,
            )
            if attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))

    logger.error("[scene_generator] %s exhausted retries: %s", label, last_exc)
    return None


# ── Internal image generation helpers ───────────────────────────────────────────

def _default_scene_size() -> str:
    """Default landscape size for scene / keyframe generation (e.g. '1280*720')."""
    from app.config import settings
    return getattr(settings, "image_size_scene", "1280*720") or "1280*720"


def _parse_size_to_tuple(size: str) -> tuple[int, int]:
    """Convert "WIDTH*HEIGHT" → (W, H) tuple. Falls back to (1024, 1024)."""
    if not size or "*" not in str(size):
        return (1024, 1024)
    try:
        w_str, h_str = str(size).split("*", 1)
        return (max(1, int(w_str)), max(1, int(h_str)))
    except (ValueError, TypeError):
        return (1024, 1024)


async def _generate_via_local(
    prompt: str,
    *,
    seed: Optional[int] = None,
    size: Optional[str] = None,
) -> Optional[str]:
    """Generate image via local Diffusers pipeline (SDXL / Z-Image)."""
    try:
        from .image_generator import get_image_generator
        generator = get_image_generator()
        out_size = size or _default_scene_size()
        size_tuple = _parse_size_to_tuple(out_size)
        image = await asyncio.to_thread(
            generator.generate, prompt, seed=seed, size=size_tuple,
        )
        if image is not None:
            return generator.pil_to_base64(image)
    except Exception as e:
        logger.warning("[scene_generator] _generate_via_local failed: %s", e)
    return None


async def _generate_via_local_with_reference(
    prompt: str,
    reference_image_b64: str,
    *,
    strength: float = 0.7,
) -> Optional[str]:
    """Generate image with style reference using local img2img pipeline."""
    try:
        from .image_generator import get_image_generator
        generator = get_image_generator()
        image = await asyncio.to_thread(
            generator.generate_with_image, prompt, reference_image_b64, strength,
        )
        if image is not None:
            return generator.pil_to_base64(image)
    except Exception as e:
        logger.warning("[scene_generator] _generate_via_local_with_reference failed: %s", e)
    return None


async def _generate_via_cloud(prompt: str, *, size: str | None = None) -> Optional[str]:
    """
    Generate image via DashScope ImageSynthesis API.

    Returns base64-encoded PNG, or None on failure.
    """
    try:
        from app.services.dashscope_client import get_dashscope_client
        client = get_dashscope_client()
        out_size = size or _default_scene_size()
        urls = await asyncio.to_thread(
            client.generate_image, prompt, size=out_size, n=1,
        )
        if not urls:
            return None
        url = urls[0]
        # Fetch and encode the image
        image_bytes = await asyncio.to_thread(_fetch_url, url)
        if image_bytes:
            return base64.b64encode(image_bytes).decode("ascii")
    except Exception as e:
        logger.warning("[scene_generator] _generate_via_cloud failed: %s", e)
    return None


def _fetch_url(url: str) -> bytes:
    """Synchronously fetch a URL (runs in thread)."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


# ── Serialisation helpers ────────────────────────────────────────────────────────

def build_scene_asset(
    scene: Scene,
    keyframe_images: Optional[dict[str, Optional[str]]] = None,
) -> SceneAsset:
    return SceneAsset(
        scene_id=scene.id,
        visual_prompt=scene.visual_prompt,
        keyframe_images=keyframe_images or {},
        variations=[],
    )


def serialize_scene_asset(asset: SceneAsset) -> dict:
    return {
        "scene_id": asset.scene_id,
        "visual_prompt": asset.visual_prompt,
        "keyframe_images": asset.keyframe_images,
        "variations": [
            {"id": v.id, "name": v.name, "visual_prompt": v.visual_prompt, "image": v.image}
            for v in asset.variations
        ],
    }
