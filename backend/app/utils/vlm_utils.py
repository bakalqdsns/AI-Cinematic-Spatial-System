"""VLM utilities — local Qwen3-VL inference."""

import asyncio
import logging
import re

from PIL import Image

from ..models import model_manager

_log = logging.getLogger("aicss.vlm")


def _vlm_chat(system_prompt: str, user_prompt: str, image: Image.Image) -> str:
    return model_manager.qwen3vl.chat(image, system_prompt, user_prompt)


SCENE_SYSTEM_PROMPT = (
    "You are a scene classification assistant. "
    "Given an image, classify it into exactly one of four scene types: "
    "'outdoor', 'indoor', 'night', or 'nature'. "
    "Reply with only the scene type word and nothing else."
)


def classify_scene(image: Image.Image) -> str:
    try:
        output = _vlm_chat(
            SCENE_SYSTEM_PROMPT,
            "What type of scene is this? Reply with only one word.",
            image,
        )
        output_lower = output.strip().lower()
        if output_lower in ("outdoor", "indoor", "night", "nature"):
            _log.info("[VLM] classify_scene -> '%s'", output_lower)
            return output_lower
        _log.warning("[VLM] classify_scene unexpected output '%s', defaulting to 'outdoor'", output)
        return "outdoor"
    except Exception as e:
        _log.error("[VLM] classify_scene EXCEPTION: %s: %s", type(e).__name__, e)
        return "outdoor"


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


def detect_objects(image: Image.Image, scene_type: str) -> str:
    user_prompt = (
        f"Describe all objects visible in this {scene_type} scene. "
        "Be thorough — include small, distant, and background objects. "
        "Return only dot-separated English class names, e.g.: person.building.car.tree.sky.road."
    )
    raw = _vlm_chat(DETECT_SYSTEM_PROMPT, user_prompt, image).strip()
    _log.info("[VLM] detect_objects raw -> '%s'", raw)
    return raw


CN_TO_EN: dict[str, str] = {
    "人物": "person", "人": "person", "人像": "person",
    "汽车": "car", "车辆": "car", "车": "car",
    "建筑": "building", "建筑物": "building", "房屋": "building",
    "树": "tree", "树木": "tree",
    "天空": "sky", "云": "cloud", "云朵": "cloud",
    "道路": "road", "马路": "road",
    "草地": "grass", "草": "grass",
    "窗户": "window", "窗": "window",
    "门": "door", "门框": "door",
    "椅子": "chair", "桌子": "table",
    "灯": "lamp", "灯柱": "lamp", "灯塔": "lamp",
    "山": "mountain", "山脉": "mountain",
    "水": "water", "河流": "water", "湖": "lake", "海洋": "sea", "大海": "sea",
    "花": "flower", "花朵": "flower",
    "卡车": "truck", "货车": "truck",
    "行人": "person",
    "雕塑": "statue", "雕像": "statue",
    "桥": "bridge", "栏杆": "railing",
    "墙壁": "wall", "墙": "wall",
    "地板": "floor", "天花板": "ceiling",
    "床": "bed", "沙发": "sofa",
    "窗帘": "curtain", "帷幕": "curtain",
    "夜景": "light", "灯光": "light",
    "灯牌": "sign", "指示牌": "sign", "标志": "sign",
    "岩石": "rock", "石头": "rock",
    "山丘": "hill", "坡": "hill",
    "动物": "animal", "狗": "dog", "猫": "cat", "鸟": "bird", "马": "horse",
    "自行车": "bicycle", "自行车道": "bicycle", "摩托车": "motorcycle",
    "飞机": "plane", "船": "boat",
    "云雾": "fog", "雾": "fog",
}


def parse_detection_result(raw: str) -> list[str]:
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
            continue
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


FALLBACK_PROMPTS: dict[str, str] = {
    "outdoor": "person.car.truck.tree.building.sky.road.grass.lamp.sign.mountain.water.flower",
    "indoor": "person.chair.table.sofa.bed.curtain.floor.wall.window.door.lamp.ceiling",
    "night": "person.car.building.light.sign.sky.window.lamp.tree.road.railing.boat",
    "nature": "tree.grass.rock.mountain.sky.cloud.water.hill.flower.bird.animal.road",
}


def get_fallback_prompt(scene_type: str) -> list[str]:
    prompt = FALLBACK_PROMPTS.get(scene_type, FALLBACK_PROMPTS["outdoor"])
    return [c.strip() for c in prompt.split(".") if c.strip()]


async def vlm_detect(image: Image.Image) -> tuple[list[str], str]:
    """
    Full VLM detection pipeline (local Qwen3-VL).

    1. Classify scene type
    2. Generate object class list
    3. Parse and deduplicate
    4. Fall back to scene-specific template on any error

    Inference is run on a worker thread to avoid blocking the event loop.
    Always returns a non-empty result — fallback is guaranteed.
    """
    try:
        scene_type = await asyncio.to_thread(classify_scene, image)
    except Exception as e:
        _log.warning("[VLM] classify_scene dispatch failed: %s: %s", type(e).__name__, e)
        scene_type = "outdoor"

    try:
        raw = await asyncio.to_thread(detect_objects, image, scene_type)
        classes = parse_detection_result(raw)
        if classes:
            _log.info("[VLM] Success -> scene=%s classes=%s", scene_type, classes)
            return classes, scene_type
        _log.warning("[VLM] Empty class list from VLM, triggering fallback")
    except Exception as e:
        _log.warning(
            "[VLM] Detection failed (%s: %s) -> fallback",
            type(e).__name__, e,
        )

    fallback = get_fallback_prompt(scene_type)
    _log.info("[VLM] Fallback scene=%s classes=%s", scene_type, fallback)
    return fallback, scene_type