"""
VLM utilities — Qwen-VL detection, scene classification, and prompt generation.

Uses the DashScope API with the Qwen-VL model to:
  1. Detect scene type (outdoor / indoor / night / nature)
  2. Generate a dot-separated list of visible object classes
  3. Fall back to scene-specific templates on failure

All API calls use the same AICSS_DASHSCOPE_API_KEY as inpainting.
"""

import io
import base64
import logging
import re
from typing import Optional

import httpx
from PIL import Image

from ..config import settings

_log = logging.getLogger("aicss.vlm")

# ── Raw HTTP helper (replaces dashscope SDK for full observability) ────────────

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

# Minimum width before we upscale for VLM
VLM_UPSCALE_MIN_W = 1024

# Target resolution for VLM input (longest edge)
VLM_TARGET_LONG_EDGE = 1280


async def _vlm_chat(
    messages: list,
    model: str,
    api_key: str,
) -> dict:
    """
    Call DashScope multimodal chat API via httpx.
    Returns the parsed JSON response dict.

    Raises httpx.HTTPStatusError on non-2xx responses for visibility.
    """
    url = f"{DASHSCOPE_BASE_URL}/services/aigc/multimodal-generation/generation"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "input": {"messages": messages},
        "parameters": {"max_tokens": 512, "temperature": 0.1},
    }

    _log.debug("[VLM] POST %s model=%s messages=%d", url, model, len(messages))

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ── Scene classification ────────────────────────────────────────────────────────

SCENE_SYSTEM_PROMPT = (
    "You are a scene classification assistant. "
    "Given an image, classify it into exactly one of four scene types: "
    "'outdoor', 'indoor', 'night', or 'nature'. "
    "Reply with only the scene type word and nothing else."
)

SCENE_CLASSIFY_MODEL = "qwen-vl-plus"


async def classify_scene(image: Image.Image, api_key: str) -> str:
    """
    Determine the scene type of an image using Qwen-VL-Plus.

    Returns one of: 'outdoor', 'indoor', 'night', 'nature'.
    Falls back to 'outdoor' on any error.
    """
    try:
        img = _prepare_for_vlm(image)
        img_b64 = _pil_to_base64(img)
        messages = [
            {
                "role": "system",
                "content": [{"text": SCENE_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{img_b64}"},
                    {"text": "What type of scene is this? Reply with only one word."},
                ],
            },
        ]

        data = await _vlm_chat(messages, SCENE_CLASSIFY_MODEL, api_key)

        _log.debug("[VLM] classify_scene raw response: %s", data)

        # Parse output — handle different response shapes
        output = _extract_text(data)
        output_lower = output.strip().lower()

        if output_lower in ("outdoor", "indoor", "night", "nature"):
            _log.info("[VLM] classify_scene -> '%s'", output_lower)
            return output_lower

        _log.warning(
            "[VLM] classify_scene unexpected output '%s' (not in valid types), defaulting to 'outdoor'",
            output,
        )
        return "outdoor"

    except Exception as e:
        _log.error("[VLM] classify_scene EXCEPTION: %s: %s", type(e).__name__, e)
        return "outdoor"


# ── Object detection ───────────────────────────────────────────────────────────

DETECT_SYSTEM_PROMPT = (
    "You are a precise scene analysis assistant. "
    "Your task is to identify ALL distinct object categories visible in the image, including small, "
    "distant, partially obscured, and background objects. "
    "Examples of commonly missed objects: street signs, pedestrians, bicycles, traffic lights, "
    "animal, fence, pillar, railing, bridge, cloud, fog, shadow, reflection, window frame, "
    "curtain, vase, book, screen, keyboard, plant, bush, shrub, stone, boulder, cliff, "
    "river, wave, puddle, snow, ice, fire, smoke. "
    "Return ONLY a single line of dot-separated English class names (all lowercase, singular nouns), "
    "e.g.: person.building.car.tree.sky.road.grass.lamp.sign.mountain.water.fence.pillar. "
    "Do NOT add explanations, counts, or any other text. Include EVERY object category you see."
)

DETECT_MODEL = "qwen-vl-max"


async def detect_objects(image: Image.Image, api_key: str, scene_type: str) -> str:
    """
    Call Qwen-VL to generate a dot-separated list of visible object classes.

    Returns a string like "person.building.car.tree" or raises on failure.
    """
    try:
        img = _prepare_for_vlm(image)
        img_b64 = _pil_to_base64(img)
        user_text = (
            f"Describe all objects visible in this {scene_type} scene. "
            "Be thorough — include small, distant, and background objects. "
            "Return only dot-separated English class names, e.g.: person.building.car.tree.sky.road."
        )
        messages = [
            {
                "role": "system",
                "content": [{"text": DETECT_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {"image": f"data:image/png;base64,{img_b64}"},
                    {"text": user_text},
                ],
            },
        ]

        data = await _vlm_chat(messages, DETECT_MODEL, api_key)

        _log.debug("[VLM] detect_objects raw response: %s", data)

        raw = _extract_text(data).strip()
        _log.info("[VLM] detect_objects raw -> '%s'", raw)
        return raw

    except Exception as e:
        _log.error("[VLM] detect_objects EXCEPTION: %s: %s", type(e).__name__, e)
        raise


def _extract_text(data: dict) -> str:
    """
    Extract the text content from a DashScope multimodal response.

    Handles the structure:
      output.choices[0].message.content[0].text
    or fallback paths.
    """
    try:
        choices = data.get("output", {}).get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", [])
            if content and isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("text"):
                        return item["text"]
            # Try direct text field
            msg = choices[0].get("message", {})
            if isinstance(msg, dict) and msg.get("text"):
                return msg["text"]
    except Exception as e:
        _log.warning("[VLM] _extract_text failed: %s", e)

    # Fallback: stringify the whole output for debugging
    _log.warning("[VLM] _extract_text could not find text in response: %s", data)
    return ""


# ── Prompt parsing ─────────────────────────────────────────────────────────────

CN_TO_EN: dict[str, str] = {
    "人物": "person",
    "人": "person",
    "人像": "person",
    "汽车": "car",
    "车辆": "car",
    "车": "car",
    "建筑": "building",
    "建筑物": "building",
    "房屋": "building",
    "树": "tree",
    "树木": "tree",
    "天空": "sky",
    "云": "cloud",
    "云朵": "cloud",
    "道路": "road",
    "马路": "road",
    "草地": "grass",
    "草": "grass",
    "窗户": "window",
    "窗": "window",
    "门": "door",
    "门框": "door",
    "椅子": "chair",
    "桌子": "table",
    "灯": "lamp",
    "灯柱": "lamp",
    "灯塔": "lamp",
    "山": "mountain",
    "山脉": "mountain",
    "水": "water",
    "河流": "water",
    "湖": "lake",
    "海洋": "sea",
    "大海": "sea",
    "花": "flower",
    "花朵": "flower",
    "卡车": "truck",
    "货车": "truck",
    "行人": "person",
    "雕塑": "statue",
    "雕像": "statue",
    "桥": "bridge",
    "栏杆": "railing",
    "墙壁": "wall",
    "墙": "wall",
    "地板": "floor",
    "天花板": "ceiling",
    "床": "bed",
    "沙发": "sofa",
    "窗帘": "curtain",
    "帷幕": "curtain",
    "夜景": "light",
    "灯光": "light",
    "灯牌": "sign",
    "指示牌": "sign",
    "标志": "sign",
    "岩石": "rock",
    "石头": "rock",
    "山丘": "hill",
    "坡": "hill",
    "动物": "animal",
    "狗": "dog",
    "猫": "cat",
    "鸟": "bird",
    "马": "horse",
    "自行车": "bicycle",
    "自行车道": "bicycle",
    "摩托车": "motorcycle",
    "飞机": "plane",
    "飞机": "airplane",
    "船": "boat",
    "船": "ship",
    "云雾": "fog",
    "雾": "fog",
}


def parse_detection_result(raw: str) -> list[str]:
    """
    Parse the raw Qwen-VL output into a list of English class names.

    Handles:
      - Dot-separated tokens (primary format)
      - Comma-separated tokens
      - Whitespace-separated tokens
      - Mixed Chinese / English
      - Duplicates and empty entries
    """
    if not raw:
        return []

    normalized = re.sub(r"[,;\n\r\t]+", ".", raw)
    tokens = [t.strip() for t in normalized.split(".") if t.strip()]

    result: list[str] = []
    for token in tokens:
        lower = token.lower()
        if re.fullmatch(r"[a-z0-9\-]+", lower):
            result.append(lower)
            continue
        if token in CN_TO_EN:
            result.append(CN_TO_EN[token])
        else:
            latin = re.sub(r"[^\x00-\x7f]", "", token).strip()
            if latin:
                result.append(latin.lower())

    seen: set[str] = set()
    unique: list[str] = []
    for item in result:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return unique


# ── Fallback templates ─────────────────────────────────────────────────────────

FALLBACK_PROMPTS: dict[str, str] = {
    "outdoor": "person.car.truck.tree.building.sky.road.grass.lamp.sign.mountain.water.flower",
    "indoor": "person.chair.table.sofa.bed.curtain.floor.wall.window.door.lamp.ceiling",
    "night": "person.car.building.light.sign.sky.window.lamp.tree.road.railing.boat",
    "nature": "tree.grass.rock.mountain.sky.cloud.water.hill.flower.bird.animal.road",
}


def get_fallback_prompt(scene_type: str) -> list[str]:
    """Return the fallback class list for a scene type."""
    prompt = FALLBACK_PROMPTS.get(scene_type, FALLBACK_PROMPTS["outdoor"])
    return [c.strip() for c in prompt.split(".") if c.strip()]


# ── Main entry point ───────────────────────────────────────────────────────────

async def vlm_detect(
    image: Image.Image,
    api_key: Optional[str] = None,
) -> tuple[list[str], str]:
    """
    Full VLM detection pipeline.

    1. Classify scene type via Qwen-VL
    2. Generate object class list via Qwen-VL
    3. Parse and deduplicate into English class names
    4. Fall back to scene-specific template on any error

    Returns:
        (list_of_class_names, scene_type)

    Always returns a non-empty result — fallback is guaranteed.
    """
    key = api_key or settings.dashscope_api_key

    if not key:
        _log.warning("[VLM] No API key available, returning fallback")
        fallback = get_fallback_prompt("outdoor")
        _log.info("[VLM] Fallback (no key) -> scene=outdoor classes=%s", fallback)
        return fallback, "outdoor"

    # Step 1: scene classification
    scene_type = await classify_scene(image, key)

    # Step 2: object detection
    try:
        raw = await detect_objects(image, key, scene_type)
        classes = parse_detection_result(raw)

        if classes:
            _log.info("[VLM] Success -> scene=%s classes=%s", scene_type, classes)
            return classes, scene_type

        # Empty result after parsing — trigger fallback
        _log.warning("[VLM] Empty class list from VLM, triggering fallback")
        raise ValueError(f"Empty class list from VLM, raw='{raw[:100]}'")

    except Exception as e:
        fallback = get_fallback_prompt(scene_type)
        _log.warning(
            "[VLM] Detection failed (%s: %s) -> fallback scene=%s classes=%s",
            type(e).__name__, e, scene_type, fallback,
        )
        return fallback, scene_type


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prepare_for_vlm(img: Image.Image) -> Image.Image:
    """
    Upscale image if needed for better VLM detection of small objects.

    - If the image's shortest edge is below VLM_UPSCALE_MIN_W, upscale to reach it.
    - Then clamp the longest edge to VLM_TARGET_LONG_EDGE to stay within API limits.
    """
    w, h = img.size
    short = min(w, h)

    if short < VLM_UPSCALE_MIN_W:
        scale = VLM_UPSCALE_MIN_W / short
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        _log.debug("[VLM] Upscaled from %dx%d to %dx%d", w, h, new_w, new_h)
        w, h = new_w, new_h

    long = max(w, h)
    if long > VLM_TARGET_LONG_EDGE:
        scale = VLM_TARGET_LONG_EDGE / long
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        _log.debug("[VLM] Scaled down from %dx%d to %dx%d", w, h, new_w, new_h)

    return img


def _pil_to_base64(img: Image.Image) -> str:
    """PIL Image -> base64 string (without data URL prefix)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")
