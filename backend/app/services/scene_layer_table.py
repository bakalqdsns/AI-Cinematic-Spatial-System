"""
闭集场景类和标签匹配表。

分层之前先给每个场景类打分，再交给现有 LLM 从闭集里选一个类名。
LLM 超时、报错或答出闭集之外的字符串时，用得分最高的类。
没有物件时直接用 unknown，不把未知标签全部丢进前景。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence

logger = logging.getLogger("aicss.scene_layers")

# 只能是这五层。匹配表里的别名必须落到其中之一。
LAYER_NAMES: tuple[str, ...] = (
    "sky",
    "background",
    "midground",
    "foreground",
    "ground",
)

# 闭集。LLM 只能从这里面选。
SCENE_CLASS_NAMES: tuple[str, ...] = (
    "school_playground",
    "park",
    "street",
    "courtyard",
    "indoor_room",
    "nature",
    "unknown",
)

# 命中一个期望标签的固定加分，再加上面积占比。面积越大分越高。
_HIT_BONUS = 2.0
_AREA_WEIGHT = 8.0
# 出现该场景不该有的强标签时扣分。大面积扣得更多。
_FORBIDDEN_BONUS = 4.0
_FORBIDDEN_AREA = 16.0

# 场景分类只需要一个类名，不让归档在本地模型上干等。
_LLM_TIMEOUT_SEC = 30.0

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CLASS_SET = frozenset(SCENE_CLASS_NAMES)


def _norm(text: object) -> str:
    return " ".join(str(text or "").strip().lower().replace("_", " ").split())


def _table(
    *,
    sky: Sequence[str] = (),
    background: Sequence[str] = (),
    midground: Sequence[str] = (),
    foreground: Sequence[str] = (),
    ground: Sequence[str] = (),
) -> dict[str, str]:
    """把别名收成「规范化标签 → 层」。同一场景里别名不能指向两层。"""
    layers = {
        "sky": sky,
        "background": background,
        "midground": midground,
        "foreground": foreground,
        "ground": ground,
    }
    out: dict[str, str] = {}
    for layer, aliases in layers.items():
        for alias in aliases:
            key = _norm(alias)
            if not key:
                continue
            previous = out.get(key)
            if previous is not None and previous != layer:
                raise ValueError(f"别名 {key!r} 同时指向 {previous} 和 {layer}")
            out[key] = layer
    return out


@dataclass(frozen=True)
class SceneClassSpec:
    """一个闭集场景类：期望标签进哪一层，以及有没有天空和地面。"""

    name: str
    has_sky: bool
    has_ground: bool
    label_layers: Mapping[str, str]
    forbidden: tuple[str, ...] = ()


def _spec(
    name: str,
    *,
    has_sky: bool,
    has_ground: bool,
    forbidden: Sequence[str] = (),
    **layers: Sequence[str],
) -> SceneClassSpec:
    return SceneClassSpec(
        name=name,
        has_sky=has_sky,
        has_ground=has_ground,
        label_layers=_table(**layers),
        forbidden=tuple(forbidden),
    )


# 人、树、长椅这些跨场景的词大家都能命中；操场、跑道、教学楼只写在学校操场里，
# 用来把这一类和公园、街道分开。unknown 不收这些专名，避免保守表和专类打成平手。
SCENE_SPECS: dict[str, SceneClassSpec] = {
    "school_playground": _spec(
        "school_playground",
        has_sky=True,
        has_ground=True,
        sky=("sky", "天空", "云", "云朵", "cloud"),
        background=("教学楼", "教学楼房", "building", "楼房", "大楼", "tree", "树", "树木", "树林"),
        midground=("bench", "长椅", "长凳", "凳子", "座椅", "fence", "围栏", "栅栏"),
        foreground=("person", "人", "人物", "行人", "people", "pedestrian", "child", "小孩", "学生", "student"),
        ground=(
            "操场", "playground", "跑道", "track", "court", "球场", "篮球场",
            "运动场", "操场地面",
        ),
        forbidden=("bed", "sofa", "ceiling", "床", "沙发", "天花板", "窗帘", "curtain", "马桶", "toilet"),
    ),
    "park": _spec(
        "park",
        has_sky=True,
        has_ground=True,
        sky=("sky", "天空", "云", "云朵", "cloud"),
        background=("tree", "树", "树木", "树林", "forest", "森林"),
        midground=("bench", "长椅", "长凳", "凳子", "座椅", "flower", "花", "花朵", "bush", "灌木"),
        foreground=("person", "人", "人物", "行人", "people", "child", "小孩", "dog", "狗"),
        ground=("grass", "草地", "草坪", "lawn", "path", "小路", "小径", "lake", "湖", "pond", "池塘", "water", "水面"),
        forbidden=(
            "操场", "跑道", "track", "court", "球场", "教学楼",
            "car", "汽车", "bed", "sofa", "ceiling", "床", "沙发", "road", "马路",
        ),
    ),
    "street": _spec(
        "street",
        has_sky=True,
        has_ground=True,
        sky=("sky", "天空", "云", "cloud"),
        background=("building", "建筑", "楼房", "大楼", "楼", "tree", "树", "树木"),
        midground=("lamp", "路灯", "streetlight", "灯", "sign", "招牌", "标志", "traffic light", "红绿灯", "pole", "杆"),
        foreground=(
            "person", "人", "人物", "行人", "pedestrian", "people",
            "car", "车", "汽车", "truck", "卡车", "bus", "公交", "bicycle", "自行车", "motorcycle",
        ),
        ground=("road", "马路", "道路", "street", "街道", "公路", "sidewalk", "人行道", "crosswalk", "斑马线", "pavement"),
        forbidden=("床", "沙发", "天花板", "bed", "sofa", "ceiling", "操场", "跑道", "track", "court", "教学楼"),
    ),
    "courtyard": _spec(
        "courtyard",
        has_sky=True,
        has_ground=True,
        sky=("sky", "天空", "云", "cloud"),
        background=("wall", "墙", "围墙", "院墙", "tree", "树", "树木"),
        midground=("bench", "石凳", "长椅", "plant", "植物", "盆栽", "door", "门", "window", "窗", "窗户"),
        foreground=("person", "人", "人物", "行人", "people"),
        ground=("courtyard", "庭院", "院子", "天井", "ground", "地面", "石板", "pavement"),
        forbidden=("car", "汽车", "操场", "跑道", "track", "road", "马路", "床", "bed", "ceiling", "天花板"),
    ),
    "indoor_room": _spec(
        "indoor_room",
        has_sky=False,
        has_ground=True,
        background=("wall", "墙", "墙壁", "ceiling", "天花板", "吊顶"),
        midground=(
            "chair", "椅子", "table", "桌子", "sofa", "沙发", "bed", "床",
            "desk", "书桌", "cabinet", "柜子", "shelf", "书架",
            "door", "门", "window", "窗", "窗户", "curtain", "窗帘",
            "lamp", "灯", "台灯", "tv", "电视", "furniture", "家具",
        ),
        foreground=("person", "人", "人物", "people"),
        ground=("floor", "地板", "地面", "ground", "地毯", "carpet"),
        # 室内不该有大面积天空、山和马路。这些词不在期望表里，只扣分。
        forbidden=(
            "sky", "天空", "cloud", "云", "云朵",
            "mountain", "山", "山脉",
            "road", "马路", "操场", "跑道", "track", "court", "球场", "playground",
        ),
    ),
    "nature": _spec(
        "nature",
        has_sky=True,
        has_ground=True,
        sky=("sky", "天空", "云", "云朵", "cloud"),
        background=("tree", "树", "树木", "树林", "forest", "森林", "mountain", "山", "山脉", "hill", "山丘"),
        midground=("rock", "石头", "岩石", "flower", "花", "花朵", "bush", "灌木"),
        foreground=("person", "人", "人物", "people", "animal", "动物", "bird", "鸟", "dog", "狗"),
        ground=("grass", "草", "草地", "dirt", "泥土", "water", "水", "river", "河", "lake", "湖", "溪流", "sand", "沙"),
        forbidden=(
            "car", "汽车", "building", "建筑", "教学楼", "楼房",
            "sofa", "bed", "沙发", "床", "ceiling", "天花板",
            "操场", "跑道", "road", "马路",
        ),
    ),
    # 保守默认：只登记跨场景都说得通的词。没登记的标签不进前景，交给深度去贴已有的层。
    "unknown": _spec(
        "unknown",
        has_sky=True,
        has_ground=True,
        sky=("sky", "天空", "云", "cloud"),
        background=("building", "建筑", "楼房", "大楼", "tree", "树", "树木", "mountain", "山", "wall", "墙", "墙壁"),
        midground=("bench", "长椅", "chair", "椅子", "table", "桌子", "lamp", "灯", "sign", "招牌"),
        foreground=("person", "人", "人物", "行人", "people", "pedestrian", "child", "car", "车", "汽车"),
        ground=("ground", "地面", "floor", "地板", "road", "路", "马路", "grass", "草地", "sidewalk", "人行道"),
        forbidden=(),
    ),
}


def _alias_hit(label_n: str, alias_n: str) -> bool:
    """英文按整词，中文两个字及以上才允许包含。单字只接受完全相同，避免「人」撞进别的词。"""
    if not label_n or not alias_n:
        return False
    if label_n == alias_n:
        return True
    if _CJK_RE.search(alias_n):
        return len(alias_n) >= 2 and alias_n in label_n
    tokens = [tok for tok in re.split(r"[\s\-./]+", label_n) if tok]
    return alias_n in tokens


def layer_for_label(spec: SceneClassSpec, label: str) -> Optional[str]:
    """标签在这张匹配表里时应去的层。表里没有就返回 None。"""
    label_n = _norm(label)
    best_layer: Optional[str] = None
    best_len = -1
    for alias, layer in spec.label_layers.items():
        alias_n = _norm(alias)
        if _alias_hit(label_n, alias_n) and len(alias_n) > best_len:
            best_layer = layer
            best_len = len(alias_n)
    return best_layer


def _forbidden(spec: SceneClassSpec, label: str) -> bool:
    label_n = _norm(label)
    return any(_alias_hit(label_n, _norm(alias)) for alias in spec.forbidden)


def _label(obj: object) -> str:
    return _norm(getattr(obj, "label", ""))


def _area(obj: object) -> float:
    meta = getattr(obj, "meta", None) or {}
    if isinstance(meta, dict) and meta.get("area_px") is not None:
        return max(0.0, float(meta["area_px"]))
    mask = getattr(obj, "mask", None)
    if mask is not None:
        try:
            return max(0.0, float(mask.sum()))
        except Exception:
            return 1.0
    return 1.0


def _vertical(obj: object) -> float:
    meta = getattr(obj, "meta", None) or {}
    if isinstance(meta, dict) and meta.get("vertical_pos") is not None:
        return float(meta["vertical_pos"])
    return 0.5


def _depth(obj: object) -> float:
    try:
        return float(getattr(obj, "depth_mean", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def object_brief(obj: object) -> dict:
    """交给 LLM 的一条物件：标签、面积、深度均值、垂直位置、框。"""
    bbox = getattr(obj, "bbox", None) or ()
    return {
        "label": _label(obj),
        "area_px": _area(obj),
        "depth_mean": round(_depth(obj), 4),
        "vertical_pos": round(_vertical(obj), 4),
        "bbox": [int(v) for v in bbox] if bbox else [],
    }


def get_scene_spec(name: Optional[str]) -> SceneClassSpec:
    """按闭集类名取表。类名里的下划线要保留，不能当成标签去折掉。"""
    key = str(name or "").strip().lower()
    return SCENE_SPECS.get(key, SCENE_SPECS["unknown"])


def score_scene_classes(objects: Sequence[object]) -> dict[str, float]:
    """按匹配表打分。命中的期望标签越多、面积越大，分越高；不该出现的强标签扣分。"""
    scores = {name: 0.0 for name in SCENE_CLASS_NAMES}
    if not objects:
        return scores
    areas = [_area(obj) for obj in objects]
    total = sum(areas) or 1.0
    for obj, area in zip(objects, areas):
        label = _label(obj)
        frac = area / total
        for spec in SCENE_SPECS.values():
            if layer_for_label(spec, label):
                scores[spec.name] += _HIT_BONUS + _AREA_WEIGHT * frac
            elif _forbidden(spec, label):
                scores[spec.name] -= _FORBIDDEN_BONUS + _FORBIDDEN_AREA * frac
    return scores


def scene_class_from_scores(scores: Mapping[str, float]) -> str:
    """取得分最高的类。全是 0 或并列且没有正分时用 unknown。"""
    best_score: Optional[float] = None
    tied: list[str] = []
    for name in SCENE_CLASS_NAMES:
        value = float(scores.get(name, 0.0))
        if best_score is None or value > best_score + 1e-9:
            best_score = value
            tied = [name]
        elif abs(value - best_score) <= 1e-9:
            tied.append(name)
    if not tied:
        return "unknown"
    if "unknown" in tied and (best_score or 0.0) <= 0.0:
        return "unknown"
    for name in SCENE_CLASS_NAMES:
        if name in tied and name != "unknown":
            return name
    return tied[0]


def parse_scene_class(text: str) -> Optional[str]:
    """只接受整段就是闭集里的一个类名。夹杂解释的回答视为无效。"""
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = cleaned.strip().strip("`\"'“”").strip().lower()
    cleaned = cleaned.strip(".,;:，。!！")
    if cleaned in _CLASS_SET:
        return cleaned
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) == 1 and lines[0] in _CLASS_SET:
        return lines[0]
    return None


def _scene_messages(objects: Sequence[object], scores: Mapping[str, float]) -> list[dict]:
    import json

    brief = [object_brief(obj) for obj in objects]
    allowed = ", ".join(SCENE_CLASS_NAMES)
    return [
        {
            "role": "system",
            "content": (
                "你是场景分类器。只能从给定闭集里选择一个场景类名。"
                "不要解释，不要输出其它文字。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"闭集: {allowed}\n"
                f"物件: {json.dumps(brief, ensure_ascii=False)}\n"
                f"规则打分: {json.dumps(dict(scores), ensure_ascii=False)}\n"
                "只回复一个类名。"
            ),
        },
    ]


async def _await_chat(client: object, messages: list[dict]) -> str:
    result = client.chat(messages, temperature=0.0, max_tokens=24)  # type: ignore[attr-defined]
    if asyncio.iscoroutine(result):
        result = await asyncio.wait_for(result, timeout=_LLM_TIMEOUT_SEC)
    return "" if result is None else str(result)


def _chat_http(client: object, messages: list[dict]) -> str:
    """用本地客户端自己的地址发同步请求。归档接口已经跑在事件循环里，不能再套一层。"""
    import httpx

    base = str(getattr(client, "base_url")).rstrip("/")
    model = getattr(client, "model")
    timeout = min(float(getattr(client, "timeout", _LLM_TIMEOUT_SEC) or _LLM_TIMEOUT_SEC), _LLM_TIMEOUT_SEC)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 24,
    }
    with httpx.Client(timeout=timeout, trust_env=False) as http:
        resp = http.post(f"{base}/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
    return str(data.get("choices", [{}])[0].get("message", {}).get("content", "") or "")


def _chat_in_thread(client: object, messages: list[dict]) -> str:
    import concurrent.futures

    def _runner() -> str:
        return asyncio.run(_await_chat(client, messages))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_runner).result(timeout=_LLM_TIMEOUT_SEC + 5.0)


def _call_default_llm(objects: Sequence[object], scores: Mapping[str, float]) -> str:
    """把物件清单和得分交给 app.services.local_llm.get_llm_client()。"""
    from app.services.local_llm import get_llm_client

    client = get_llm_client()
    messages = _scene_messages(objects, scores)
    # 本地客户端有地址和模型名。云端代理没有，改走它自己的 chat。
    if getattr(client, "base_url", None) and getattr(client, "model", None):
        return _chat_http(client, messages)
    return _chat_in_thread(client, messages)


def classify_scene(
    objects: Sequence[object],
    *,
    llm_call: Optional[Callable[[Sequence[object], Mapping[str, float]], str]] = None,
) -> str:
    """先打分，再让 LLM 从闭集里选。失败或答非所问时用最高分。没有物件时用 unknown。"""
    scores = score_scene_classes(objects)
    fallback = scene_class_from_scores(scores)
    if not objects:
        return "unknown"
    try:
        if llm_call is None:
            raw = _call_default_llm(objects, scores)
        else:
            raw = llm_call(list(objects), dict(scores))
    except Exception as exc:
        logger.warning("[scene] LLM 场景分类失败，改用得分最高的类 %s: %s", fallback, exc)
        return fallback
    parsed = parse_scene_class("" if raw is None else str(raw))
    if parsed is None:
        logger.info("[scene] LLM 返回闭集之外 %r，改用 %s", raw, fallback)
        return fallback
    return parsed
