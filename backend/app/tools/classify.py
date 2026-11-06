"""场景类识别工具 —— 闭集场景分类。

包装 ``app.services.scene_layer_table``。先按匹配表规则打分，再让 LLM
从闭集里选一个类名；LLM 失败或答非所问时退回得分最高的类。测试时可用
``llm_call`` 注入假回答，完全避开 LLM。
"""
from __future__ import annotations

from typing import Callable, Optional

__all__ = ["classify_scene", "scene_class_scores"]


def classify_scene(objects: list, llm_call: Optional[Callable] = None) -> str:
    """把检测到的物件列表归到一个闭集场景类。

    输入:
        objects: 物件列表（``detect_objects(...).objects``，或任何带
            label / meta.area_px / depth_mean 属性的对象列表）。空列表
            直接返回 "unknown"，不调 LLM。
        llm_call: 可选的自定义分类回调，签名
            ``llm_call(objects, scores) -> str``。None 时用默认本地 LLM；
            测试时传 ``lambda objs, scores: "park"`` 即可避开 LLM。
    输出:
        闭集类名之一："school_playground" / "park" / "street" /
        "courtyard" / "indoor_room" / "nature" / "unknown"。
    副作用:
        无。llm_call=None 时可能向本地 llama.cpp 发一次请求（30s 超时，
        失败自动退回规则打分）。
    模型:
        本地 Qwen2.5-7B（llama.cpp），可选；规则打分始终可用。
    """
    from app.services.scene_layer_table import classify_scene as _classify

    return _classify(list(objects or []), llm_call=llm_call)


def scene_class_scores(objects: list) -> dict:
    """只跑规则打分，不调 LLM（纯函数）。

    输入:
        objects: 物件列表，同 ``classify_scene``。
    输出:
        dict，{场景类名: 分数}，覆盖闭集全部 7 个类。分数越高越像；
        命中期望标签加分，出现禁忌标签扣分。
    副作用:
        无。
    模型:
        无。
    """
    from app.services.scene_layer_table import score_scene_classes

    return score_scene_classes(list(objects or []))
