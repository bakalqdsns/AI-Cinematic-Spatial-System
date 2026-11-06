"""视觉提示词工具 —— 把角色/场景描述变成英文出图提示词。

包装 ``app.services.character_generator.generate_visual_prompt`` 和
``app.services.scene_generator.generate_scene_visual_prompt``。
输入输出都是 dict / str，不依赖 FastAPI，不直接读全局 settings。

注意：底层服务按 settings.model_mode 决定走本地 llama.cpp 还是云端
DashScope；工具本身不读这个配置，由调用方在部署环境预设。LLM 不可用
时自动退回模板拼接的提示词。
"""
from __future__ import annotations

from app.services.script_parser import Character, Scene
from app.tools._shared import to_language

__all__ = ["character_visual_prompt", "scene_visual_prompt"]


async def character_visual_prompt(
    character: dict,
    genre: str = "cinematic",
    language: str = "chinese",
) -> str:
    """为一个角色生成英文视觉提示词（用于三视图/参考图出图）。

    输入:
        character: 角色 dict，至少含 name；可含 gender / age /
            personality（即 ``extract_characters`` 的输出项）。
        genre: 题材风格，如 "cinematic" / "animation" / "fantasy"。
        language: "chinese" / "english" / "japanese"。
    输出:
        英文视觉提示词（str）。
    副作用:
        无。可能向 LLM（本地或云端）发一次请求；失败时退回模板提示词。
    模型:
        LLM（本地 llama.cpp 或云端，取决于部署 settings），可选。
    """
    from app.services.character_generator import generate_visual_prompt

    char = Character.from_dict(character)
    return await generate_visual_prompt(char, genre=genre, language=to_language(language))


async def scene_visual_prompt(
    scene: dict,
    genre: str = "cinematic",
    language: str = "chinese",
) -> str:
    """为一个场景生成英文视觉提示词（用于场景关键帧出图）。

    输入:
        scene: 场景 dict，至少含 location；可含 time / atmosphere
            （即 ``parse_script_text`` 输出里的 scenes 项）。
        genre: 题材风格。
        language: "chinese" / "english" / "japanese"。
    输出:
        英文视觉提示词（str）。只描述地点，不含人物和动作。
    副作用:
        无。可能向 LLM 发一次请求；失败时退回模板提示词。
    模型:
        LLM（本地 llama.cpp 或云端，取决于部署 settings），可选。
    """
    from app.services.scene_generator import generate_scene_visual_prompt

    sc = Scene.from_dict(scene)
    return await generate_scene_visual_prompt(sc, genre=genre, language=to_language(language))
