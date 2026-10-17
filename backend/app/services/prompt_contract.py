"""四条可复制提示词的写作合同和本地检查。检查不调用模型。"""
from __future__ import annotations

import re

CHARACTER_SYSTEM = """你是视觉提示词作者。根据角色事实写一段可直接粘贴到外部绘图软件的英文主提示词。

这是一张正面人物参考图，不是剧情镜头。
- 画面里恰好一个人，写出 Exactly one person。
- 分开写稳定身份（脸型、体型、发型、一个固定标志）和当前服装。
- 中性站姿，重心落在双脚，目光看向镜头，正面。
- 纯色或简单背景，不要场景、不要其他人和倒影里的人。
- 写一个具体主光源和方向，例如 soft key light from the front-left。
- 性格只转成可见的姿态或神情，不要写成风格口号。
- 不要默认动漫、纸艺、纸板或 cardboard。只有题材事实里明确要求时才写那种媒介。
- 不要逗号关键词堆砌，写成连贯英文段落。
- 只输出提示词正文，不要解释、标题或引号。"""

SCENE_SYSTEM = """你是视觉提示词作者。根据场景事实写一段可直接粘贴到外部绘图软件的英文主提示词。

这是一张给深度分层用的 16:9 空场景 wide 图。
- 明确写出 no people, no animals。
- 前景、中景、背景各写一个固定、可数的锚点，并说明它们的左右和远近。
- 只写一个主光源、它的方向和软硬，让三层深度能分开。
- 写材质对这束光的不同反应，不要所有表面都变成同一种塑料。
- 氛围写成可看见的天气、时间或光线，不要写成 cinematic、epic 这类空词。
- 不要默认纸艺、纸板、cardboard、anime background。只有地点事实里明确是那种材质时才写。
- 写成连贯英文段落，不要逗号关键词表。
- 只输出提示词正文，不要解释、标题或引号。"""

ACTION_SYSTEM = """动作提示词是给外部软件生成人物表演视频的英文正文，用来抽帧和分割，不是第二条成片。
- 写出 Exactly N people，N 等于本分镜列出的人数，未列出的人不出现，不要群众。
- 继承已给出的角色身份句，不要改写成另一个人。
- 写明时长。Open: 起始姿态、目光和手脚。接着用时间段写准备、施力、接触、落地。Close: 结束姿态。
- 运镜只用给出的那一种，并写 camera start 和 camera end。不要同时写第二种运镜。
- 人物身体要留在画面里，便于分割。
- 不要重写整段场景，不要纸艺或动漫口号。
- 只输出英文正文。"""


def _low(text: str) -> str:
    return (text or "").lower()


def _has_exact_count(text: str) -> bool:
    return bool(re.search(r"\bexactly\s+(one|two|three|four|\d+)\b", _low(text)))


def _has_specific_light(text: str) -> bool:
    low = _low(text)
    sources = (
        "sun", "lamp", "window", "key light", "moon", "neon", "firelight",
        "bulb", "skylight", "daylight", "moonlight", "practical",
    )
    directions = (
        "from the", "from screen", "from above", "from behind", "from camera",
        "screen-left", "screen-right", "front-left", "front-right",
        "camera-left", "camera-right",
    )
    return any(word in low for word in sources) and any(word in low for word in directions)


def _style_issues(text: str) -> list[str]:
    low = _low(text)
    if any(word in low for word in ("paper-craft", "papercraft", "cardboard", "craft-paper", "anime art")):
        return ["出现了不该默认的纸艺或动漫风格"]
    return []


_CAMERA_FAMILIES = {
    "dolly": ("dolly", "push in", "push-in", "pull out", "pull-out"),
    "pan": ("pan ", "pan left", "pan right"),
    "tilt": ("tilt",),
    "zoom": ("zoom",),
    "crane": ("crane",),
    "orbit": ("orbit",),
    "track": ("tracking", "track left", "track right"),
    "handheld": ("handheld",),
}


def _camera_families(text: str) -> list[str]:
    low = _low(text)
    return [name for name, keys in _CAMERA_FAMILIES.items() if any(key in low for key in keys)]


def check_character_prompt(text: str) -> list[str]:
    low = _low(text)
    issues: list[str] = []
    if not _has_exact_count(text):
        issues.append("没有写明画面里恰好有几个人")
    if not any(word in low for word in ("face", "hair", "build", "shoulder")):
        issues.append("没有写下能认出同一个人的身份")
    if not any(word in low for word in ("wear", "wearing", "clothes", "clothing", "dressed", "coat", "shirt", "dress", "jacket", "uniform")):
        issues.append("没有写当前服装")
    if not any(word in low for word in ("front view", "facing the camera", "facing camera", "looks at the camera", "looking at the camera")):
        issues.append("没有写成正面、看向镜头")
    if not any(word in low for word in ("plain background", "simple background", "solid background", "neutral background")):
        issues.append("没有写成简单背景")
    if not _has_specific_light(text):
        issues.append("光源不够具体")
    issues.extend(_style_issues(text))
    return issues


def check_scene_prompt(text: str) -> list[str]:
    low = _low(text)
    issues: list[str] = []
    if not any(word in low for word in ("no people", "no person", "nobody", "empty of people")):
        issues.append("没有声明场景里没有人")
    if "foreground" not in low or "background" not in low or ("midground" not in low and "mid-ground" not in low):
        issues.append("没有写全前景、中景和背景")
    if not _has_specific_light(text):
        issues.append("光源不够具体")
    if "16:9" not in text and "widescreen" not in low:
        issues.append("没有写成 16:9 全景")
    issues.extend(_style_issues(text))
    return issues


def check_action_prompt(text: str) -> list[str]:
    low = _low(text)
    issues: list[str] = []
    if not _has_exact_count(text):
        issues.append("没有写明画面里恰好有几个人")
    if not any(word in low for word in ("open:", "open state", "first frame", "starting pose")):
        issues.append("没有写起始姿态")
    if not any(word in low for word in ("close:", "final frame", "end state", "ending pose")):
        issues.append("没有写结束姿态")
    families = _camera_families(text)
    if len(families) > 1:
        issues.append("同时写了不止一种运镜")
    elif not families and "static" not in low and "camera" not in low:
        issues.append("没有写运镜的起点和终点")
    return issues


def check_v2v_prompt(text: str) -> list[str]:
    issues: list[str] = []
    if "必须保持" not in text:
        issues.append("没有写必须保持的部分")
    if "只允许改变" not in text:
        issues.append("没有写只允许改变的部分")
    if "参考视频是本条渲染结果" not in text:
        issues.append("没有写参考视频是本条渲染结果")
    if "（还没有填写）" in text:
        issues.append("还没有写允许改变的那一句")
    return issues


def build_v2v_prompt(sentence: str) -> str:
    change = sentence.strip() or "（还没有填写）"
    return (
        "必须保持：已渲染的场景分层、机位和这条分镜已有的动作。未写到的身份、空间和时长保持不变。\n"
        f"只允许改变：{change}\n"
        "参考视频是本条渲染结果。"
    )


def _light_for_time(time_name: str) -> str:
    table = {
        "day": "sunlight from screen-left, high and moderately hard",
        "night": "one practical lamp from the midground, soft and limited",
        "dawn": "low sun from screen-right, soft",
        "dusk": "low sun from screen-left, warm and moderately hard",
        "morning": "soft daylight from screen-right",
        "evening": "one warm practical lamp from the midground, with dim skylight from above",
    }
    return table.get((time_name or "").lower(), "one key light from screen-left")


def fallback_character_prompt(name: str, gender: str = "", age: str = "", personality: str = "") -> str:
    who = ", ".join(part for part in (age, gender) if part) or "adult"
    manner = personality.strip() or "calm"
    label = name.strip() or "the subject"
    return (
        f"Exactly one person in frame: {label}, a {who}. "
        f"Identity anchors: the same face shape, build, hair, and one small fixed mark stay unchanged. "
        f"Current clothing is a simple everyday outfit; the {manner} manner shows only in a quiet expression. "
        "Neutral standing pose, weight on both feet, front view, looking at the camera. "
        "Plain background, no location and no other people. "
        "Soft key light from the front-left."
    )


def fallback_scene_prompt(location: str, time_name: str = "Day", atmosphere: str = "") -> str:
    place = location.strip() or "the location"
    weather = atmosphere.strip() or "clear air"
    light = _light_for_time(time_name)
    return (
        f"Empty location, no people and no animals. {place} during {time_name or 'Day'}. "
        f"Foreground: one grounded object close to the camera. "
        f"Midground: the main usable area of {place}. "
        f"Background: one distant anchor that sets depth. "
        f"Key light is {light}, so the three depths separate. "
        f"Matte surfaces stay dull and any glossy surface catches only that key light. "
        f"Observable condition: {weather}. 16:9 widescreen establishing view."
    )


def fallback_action_prompt(
    names: list[str],
    identities: list[str],
    summary: str,
    duration: float,
    camera: str,
    shot_size: str,
) -> str:
    people = [name for name in names if name] or ["the subject"]
    count = len(people)
    word = {1: "one", 2: "two", 3: "three", 4: "four"}.get(count, str(count))
    identity = " ".join(part.strip() for part in identities if part.strip()) or "Keep the listed faces, hair, and clothing unchanged."
    action = (summary or "hold a readable action").strip()
    seconds = duration if duration and duration > 0 else 4.0
    mid = round(seconds / 2, 1)
    motion = (camera or "Static").strip()
    size = (shot_size or "Medium Shot").strip()
    return (
        f"Exactly {word} people in frame: {', '.join(people)}. No one else and no crowd. {identity} "
        f"Duration {seconds:g}s. Open: starting pose with both hands and the gaze visible. "
        f"0.0–{mid:g}s prepare and begin: {action}. "
        f"{mid:g}–{seconds:g}s make contact, react, and settle. "
        f"Close: ending pose held, same people, same clothing. "
        f"Camera start: {size}, subject readable. Camera path: {motion} only. "
        f"Camera end: the same subject still in frame. Full body or the named framing stays segmentable."
    )
