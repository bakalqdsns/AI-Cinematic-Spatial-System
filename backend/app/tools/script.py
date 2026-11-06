"""剧本解析工具 —— 《纸间行》链路第一步。

把 ``app.services.script_parser`` 和 ``app.services.shot_generator`` 的
能力包装成独立函数：输入输出都是 dict，不依赖 FastAPI，不直接读全局
settings。LLM（本地 llama.cpp）不可用时，底层自动退回启发式解析，
所以离线也能拿到结构化结果。

能力清单：
- normalize_script_text : 原始剧本 → 标准格式文本
- parse_script_text     : 剧本 → 结构化 ScriptData dict
- extract_characters    : 剧本 → 角色 dict 列表
- generate_shots        : ScriptData dict → 分镜 dict 列表
"""
from __future__ import annotations

from typing import Optional

from app.services.script_parser import ScriptData
from app.tools._shared import to_language

__all__ = [
    "normalize_script_text",
    "parse_script_text",
    "extract_characters",
    "generate_shots",
]


async def normalize_script_text(raw_text: str, language: str = "chinese") -> str:
    """把原始剧本文本规范化成标准剧本格式（Pass 1）。

    输入:
        raw_text: 原始剧本文本（中文/英文/日文均可）。
        language: "chinese" / "english" / "japanese"。
    输出:
        规范化后的剧本文本（str）。
    副作用:
        无。可能向本地 llama.cpp 服务器发一次请求；失败时退回简单排版。
    模型:
        本地 Qwen2.5-7B（llama.cpp），可选；缺失时自动降级。
    """
    from app.services.script_parser import normalize_script

    return await normalize_script(raw_text, to_language(language))


async def parse_script_text(
    text: str,
    language: str = "chinese",
    normalize: bool = False,
) -> dict:
    """把剧本文本解析成结构化 ScriptData（Pass 2）。

    输入:
        text: 剧本文本。``normalize=True`` 时先做 Pass 1 规范化。
        language: "chinese" / "english" / "japanese"。
        normalize: 是否先跑规范化再解析。
    输出:
        dict，字段为 title / genre / logline / characters / scenes /
        story_paragraphs / language（ScriptData.to_dict() 的形状）。
    副作用:
        无。可能向本地 llama.cpp 发若干次请求；任一子任务失败只影响
        对应字段，整体退回启发式解析，不会抛异常。
    模型:
        本地 Qwen2.5-7B（llama.cpp），可选；缺失时自动降级。
    """
    from app.services.script_parser import normalize_script, parse_script

    lang = to_language(language)
    if normalize:
        text = await normalize_script(text, lang)
    script = await parse_script(text, lang)
    return script.to_dict()


async def extract_characters(text: str, language: str = "chinese") -> list[dict]:
    """只提取剧本里的真实人类角色（character-first 管线第一步）。

    输入:
        text: 剧本文本（原始或规范化后的均可）。
        language: "chinese" / "english" / "japanese"。
    输出:
        角色 dict 列表，每项含 id / name / gender / age / personality /
        visual_prompt / reference_image。伪角色（"特写"、"裂缝" 等）
        已被过滤。
    副作用:
        无。LLM 不可用时退回括号描述 + 对白前缀的启发式提取。
    模型:
        本地 Qwen2.5-7B（llama.cpp），可选；缺失时自动降级。
    """
    from app.services.script_parser import extract_characters as _extract

    chars = await _extract(text, to_language(language))
    return [c.to_dict() for c in chars]


async def generate_shots(
    script_data: dict,
    shots_per_scene: int = 6,
    language: Optional[str] = None,
) -> list[dict]:
    """由结构化剧本生成分镜表。

    输入:
        script_data: ``parse_script_text`` 的输出 dict（内部用
            ``ScriptData.from_dict`` 还原）。
        shots_per_scene: 每个场景的最少分镜数（LLM 可以生成更多）。
        language: 覆盖剧本自带语言；None 时用 script_data["language"]。
    输出:
        分镜 dict 列表，按 shot_number 全局连续排序；每项含 id /
        scene_id / shot_number / action_summary / dialogue /
        camera_movement / shot_size / characters / visual_prompts /
        duration_seconds / keyframe_start_prompt / keyframe_end_prompt。
    副作用:
        无。LLM 不可用时按段落类型启发式生成分镜。
    模型:
        本地 Qwen2.5-7B（llama.cpp），可选；缺失时自动降级。
    """
    from app.services.shot_generator import (
        generate_shots as _generate,
        serialize_shots,
    )

    data = ScriptData.from_dict(script_data)
    lang = to_language(language) if language else None
    shots = await _generate(data, shots_per_scene=shots_per_scene, language=lang)
    return serialize_shots(shots)
