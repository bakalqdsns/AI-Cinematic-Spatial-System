"""
Character Generator Service
===========================
Generates character reference images and three-view turnarounds.

Mode routing:
  - image_mode == "cloud" → DashScope ImageSynthesis API (no img2img fallback)
  - image_mode == "local"  → local Diffusers (Z-Image / SDXL)
  - model_mode  == "cloud" → DashScope LLM for prompt generation
  - model_mode  == "local" → local llama.cpp LLM
"""
import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from .script_parser import Character, ScriptLanguage

THREE_VIEWS = ["front", "side", "back"]

GENERATE_VISUAL_PROMPT_CHINESE = """你是一个专业的视觉提示词生成师。请为以下角色生成英文视觉描述提示词。

要求：
1. 输出纯英文描述，逗号分隔，最多50词
2. 描述角色的外貌特征、服装、姿态、表情
3. 使用电影/动画风格的视觉语言
4. 不要解释，只输出提示词

示例：
beautiful young woman, long flowing hair, red dress, standing pose, confident expression, cinematic lighting, anime art style"""

GENERATE_VISUAL_PROMPT_ENGLISH = """You are a professional visual prompt engineer. Generate English visual description prompts for the following character.

Requirements:
1. Pure English, comma-separated, max 50 words
2. Describe appearance, clothing, pose, expression
3. Use cinematic/animation visual language
4. Output only the prompt, no explanation"""

GENERATE_VISUAL_PROMPT_JAPANESE = """あなたはプロフェッショナルなビジュアルプロンプトエンジニアです。以下のキャラクターの英語のビジュアル説明プロンプトを生成してください。

要件：
1. 純粋な英語、カンマ区切り、最大50語
2. 外見、服装、ポーズ、表情を描述
3. 映画/アニメスタイルのビジュアル言語を使用"""


@dataclass
class CharacterAsset:
    character_id: str
    visual_prompt: str
    reference_image: Optional[str] = None  # base64
    three_view_images: dict[str, Optional[str]] = field(default_factory=dict)
    variations: list["CharacterVariation"] = field(default_factory=list)


@dataclass
class CharacterVariation:
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


# ── LLM: visual prompt generation ─────────────────────────────────────────────

async def generate_visual_prompt(
    character: Character,
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> str:
    """
    Generate English visual art prompt for a character.
    Routes through settings.model_mode: cloud → DashScope, local → llama.cpp.
    """
    prompts = {
        ScriptLanguage.CHINESE: GENERATE_VISUAL_PROMPT_CHINESE,
        ScriptLanguage.ENGLISH: GENERATE_VISUAL_PROMPT_ENGLISH,
        ScriptLanguage.JAPANESE: GENERATE_VISUAL_PROMPT_JAPANESE,
    }
    system_prompt = prompts[language]

    user_text = f"""角色名: {character.name}
性别: {character.gender}
年龄: {character.age}
性格: {character.personality}
题材风格: {genre}

请生成视觉描述提示词："""

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
            logger.warning("[character_generator] DashScope LLM visual prompt failed: %s", e)
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
            logger.warning("[character_generator] Local LLM visual prompt failed: %s", e)

    # Fallback
    return f"{character.name}, {character.gender}, {character.age} years old, {character.personality} personality, cinematic style"


# ── Image: reference generation ────────────────────────────────────────────────

async def generate_character_reference(
    character: Character,
    visual_prompt: Optional[str] = None,
    provider: str = "local",
) -> Optional[str]:
    """
    Generate character reference image.
    Routes through settings.image_mode: cloud → DashScope, local → local Diffusers.
    Returns base64-encoded PNG image.
    """
    prompt = visual_prompt or character.visual_prompt
    if not prompt:
        prompt = await generate_visual_prompt(character)

    image_mode = _get_image_mode()

    if image_mode == "cloud":
        return await _generate_via_cloud(prompt)
    else:
        return await _generate_via_local(prompt)


# ── Image: three-view ──────────────────────────────────────────────────────────

async def generate_character_three_view(
    character: Character,
    visual_prompt: Optional[str] = None,
    *,
    reference_image: Optional[str] = None,
    seed: Optional[int] = None,
    max_retries: int = 2,
) -> dict[str, Optional[str]]:
    """
    Generate three-view (front/side/back) character reference images.

    Strategy:
      1. Generate a "reference image" (front view, neutral pose) — this anchors
         the character's look across all three views.
      2. Use img2img with that reference for the side/back views, so the
         character stays recognisable across angles.

    If ``reference_image`` is provided, step 1 is skipped (use the supplied
    image as the visual anchor) and we only generate side/back via img2img.

    Returns dict with keys: front, side, back (base64 images).
    Each call is retried up to ``max_retries`` times on transient failures.
    """
    base_prompt = visual_prompt or character.visual_prompt
    if not base_prompt:
        base_prompt = await generate_visual_prompt(character)

    results: dict[str, Optional[str]] = {"front": None, "side": None, "back": None}

    # ── Step 1: anchor with reference image (front view) ─────────────────────
    if reference_image:
        logger.info("[character_generator] reusing supplied reference for %s", character.id)
        anchor_b64 = reference_image
        results["front"] = anchor_b64
    else:
        anchor_prompt = (
            f"{base_prompt}, character sheet, front view, facing camera, neutral pose, "
            f"full body, white background, concept art, anime style, high detail"
        )
        anchor_b64 = await _generate_with_retry(anchor_prompt, label=f"{character.id}:anchor", seed=seed)
        results["front"] = anchor_b64

    # ── Step 2: side / back views via img2img of the anchor ──────────────────
    if anchor_b64:
        side_prompt = (
            f"{base_prompt}, side profile view, 90 degree angle, full body, "
            f"same character, same outfit, same art style, white background"
        )
        back_prompt = (
            f"{base_prompt}, back view, from behind, full body, same character, "
            f"same outfit, same art style, white background"
        )
        results["side"] = await _img2img_with_retry(
            side_prompt, anchor_b64, label=f"{character.id}:side", strength=0.7,
        )
        results["back"] = await _img2img_with_retry(
            back_prompt, anchor_b64, label=f"{character.id}:back", strength=0.7,
        )

    return results


async def _generate_with_retry(
    prompt: str,
    *,
    label: str,
    seed: Optional[int] = None,
    max_retries: int = 2,
) -> Optional[str]:
    """Generate via txt2img with retry/backoff."""
    last_exc = None
    image_mode = _get_image_mode()

    for attempt in range(max_retries + 1):
        try:
            if image_mode == "cloud":
                return await _generate_via_cloud(prompt)
            else:
                return await _generate_via_local(prompt, seed=seed)
        except Exception as e:
            last_exc = e
            logger.warning(
                "[character_generator] %s attempt %d failed (mode=%s): %s",
                label, attempt + 1, image_mode, e,
            )
            if attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))

    logger.error("[character_generator] %s exhausted retries: %s", label, last_exc)
    return None


async def _img2img_with_retry(
    prompt: str,
    anchor_b64: str,
    *,
    label: str,
    strength: float = 0.7,
    max_retries: int = 2,
) -> Optional[str]:
    """Generate via img2img with retry/backoff."""
    last_exc = None
    image_mode = _get_image_mode()

    for attempt in range(max_retries + 1):
        try:
            if image_mode == "cloud":
                # DashScope doesn't natively support img2img — fall back to txt2img
                return await _generate_via_cloud(prompt)
            else:
                return await _generate_via_local_with_reference(prompt, anchor_b64, strength=strength)
        except Exception as e:
            last_exc = e
            logger.warning(
                "[character_generator] %s attempt %d failed (mode=%s): %s",
                label, attempt + 1, image_mode, e,
            )
            if attempt < max_retries:
                await asyncio.sleep(0.6 * (attempt + 1))

    logger.error("[character_generator] %s exhausted retries: %s", label, last_exc)
    return None


async def generate_character_variation(
    character: Character,
    variation_prompt: str,
    reference_image_b64: Optional[str] = None,
) -> Optional[str]:
    """
    Generate character wardrobe/outfit variation.
    If reference_image_b64 is provided, uses it as style reference for consistency.
    Returns base64 image.
    """
    image_mode = _get_image_mode()

    if image_mode == "cloud":
        return await _generate_via_cloud(variation_prompt)

    if reference_image_b64:
        return await _generate_via_local_with_reference(variation_prompt, reference_image_b64)
    else:
        return await _generate_via_local(variation_prompt)


# ── Internal image generation helpers ────────────────────────────────────────────

async def _generate_via_local(
    prompt: str,
    *,
    seed: Optional[int] = None,
) -> Optional[str]:
    """Generate image via local Diffusers pipeline (SDXL / Z-Image)."""
    try:
        from .image_generator import get_image_generator
        generator = get_image_generator()
        image = await asyncio.to_thread(generator.generate, prompt, seed=seed)
        if image is not None:
            return generator.pil_to_base64(image)
    except Exception as e:
        logger.warning("[character_generator] _generate_via_local failed: %s", e)
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
            generator.generate_with_image,
            prompt, reference_image_b64, strength,
        )
        if image is not None:
            return generator.pil_to_base64(image)
    except Exception as e:
        logger.warning("[character_generator] _generate_via_local_with_reference failed: %s", e)
    return None


async def _generate_via_cloud(prompt: str) -> Optional[str]:
    """
    Generate image via DashScope ImageSynthesis API.

    Returns base64-encoded PNG, or None on failure.
    """
    try:
        from app.services.dashscope_client import get_dashscope_client
        client = get_dashscope_client()
        urls = await asyncio.to_thread(
            client.generate_image, prompt, size="1024*1024", n=1,
        )
        if not urls:
            return None
        url = urls[0]
        image_bytes = await asyncio.to_thread(_fetch_url, url)
        if image_bytes:
            return base64.b64encode(image_bytes).decode("ascii")
    except Exception as e:
        logger.warning("[character_generator] _generate_via_cloud failed: %s", e)
    return None


def _fetch_url(url: str) -> bytes:
    """Synchronously fetch a URL (runs in thread)."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


# ── Serialisation helpers ───────────────────────────────────────────────────────

def build_character_asset(
    character: Character,
    reference_image: Optional[str] = None,
    three_view_images: Optional[dict[str, str]] = None,
) -> CharacterAsset:
    """Build CharacterAsset from Character data."""
    return CharacterAsset(
        character_id=character.id,
        visual_prompt=character.visual_prompt,
        reference_image=reference_image,
        three_view_images=three_view_images or {},
        variations=[],
    )


def serialize_character_asset(asset: CharacterAsset) -> dict:
    return {
        "character_id": asset.character_id,
        "visual_prompt": asset.visual_prompt,
        "reference_image": asset.reference_image,
        "three_view_images": asset.three_view_images,
        "variations": [
            {"id": v.id, "name": v.name, "visual_prompt": v.visual_prompt, "image": v.image}
            for v in asset.variations
        ],
    }
