"""
Character Generator Service
Generates character reference images and three-view turnarounds.

Uses local models:
  - LLM: llama.cpp Qwen3.5-9B-GGUF (via local_llm)
  - Image: Stable Diffusion XL / Z-Image (via image_generator)
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image

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


# ── LLM: visual prompt generation ─────────────────────────────────────────────

async def generate_visual_prompt(
    character: Character,
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> str:
    """
    Generate English visual art prompt for a character using local LLM.
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
        logger.warning("[character_generator] LLM visual prompt failed: %s", e)

    # Fallback
    return f"{character.name}, {character.gender}, {character.age} years old, {character.personality} personality, cinematic style"


# ── Image: reference generation ────────────────────────────────────────────────

async def generate_character_reference(
    character: Character,
    visual_prompt: Optional[str] = None,
    provider: str = "local",
) -> Optional[str]:
    """
    Generate character reference image using local image generator.
    Returns base64-encoded PNG image.
    """
    prompt = visual_prompt or character.visual_prompt
    if not prompt:
        prompt = await generate_visual_prompt(character)

    if provider == "local":
        return await _generate_via_local(prompt)
    else:
        logger.warning("[character_generator] Unknown image provider %r — using local", provider)
        return await _generate_via_local(prompt)


async def generate_character_three_view(
    character: Character,
    visual_prompt: Optional[str] = None,
) -> dict[str, Optional[str]]:
    """
    Generate three-view (front/side/back) character reference images.
    Returns dict with keys: front, side, back (base64 images).
    """
    base_prompt = visual_prompt or character.visual_prompt
    if not base_prompt:
        base_prompt = await generate_visual_prompt(character)

    view_prompts = {
        "front": f"{base_prompt}, front view, facing camera, neutral pose, full body",
        "side": f"{base_prompt}, side profile view, 90 degree angle, standing pose, full body",
        "back": f"{base_prompt}, back view, from behind, standing pose, full body",
    }

    results: dict[str, Optional[str]] = {}
    for view, view_prompt in view_prompts.items():
        try:
            image_b64 = await _generate_via_local(view_prompt)
            results[view] = image_b64
        except Exception as e:
            logger.warning("[character_generator] Failed to generate %s view: %s", view, e)
            results[view] = None

    return results


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
    if reference_image_b64:
        return await _generate_via_local_with_reference(variation_prompt, reference_image_b64)
    else:
        return await _generate_via_local(variation_prompt)


# ── Internal image generation helpers ───────────────────────────────────────────

async def _generate_via_local(prompt: str) -> Optional[str]:
    """Generate image via local Diffusers pipeline (SDXL / Z-Image)."""
    try:
        from .image_generator import get_image_generator
        generator = get_image_generator()
        image = generator.generate(prompt)
        if image is not None:
            return generator.pil_to_base64(image)
    except Exception as e:
        logger.warning("[character_generator] _generate_via_local failed: %s", e)
    return None


async def _generate_via_local_with_reference(
    prompt: str,
    reference_image_b64: str,
) -> Optional[str]:
    """Generate image with style reference using local img2img pipeline."""
    try:
        from .image_generator import get_image_generator
        generator = get_image_generator()
        image = generator.generate_with_image(prompt, reference_image_b64, strength=0.65)
        if image is not None:
            return generator.pil_to_base64(image)
    except Exception as e:
        logger.warning("[character_generator] _generate_via_local_with_reference failed: %s", e)
    return None


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
