"""出图工具 —— 场景关键帧与人物三视图。

包装 ``app.services.scene_generator`` / ``app.services.character_generator``。
输入输出都是 dict / base64 字符串，不依赖 FastAPI，不直接读全局 settings。

注意：底层按 settings.image_mode 决定走本地 Diffusers / ComfyUI Z-Image
还是云端 DashScope；工具本身不读这个配置。所有返回图像都是 base64 PNG
字符串（不带 data: 前缀），生成失败的视角为 None。
"""
from __future__ import annotations

from typing import Optional

from app.services.script_parser import Character, Scene

__all__ = ["scene_keyframes", "character_three_view", "character_variation"]


async def scene_keyframes(
    scene: dict,
    visual_prompt: Optional[str] = None,
    anchor_image_b64: Optional[str] = None,
    seed: Optional[int] = None,
    size: Optional[str] = None,
    max_retries: int = 2,
) -> dict:
    """生成场景三关键帧：wide / closeup / mood。

    输入:
        scene: 场景 dict（``parse_script_text`` 输出里的 scenes 项）。
        visual_prompt: 英文场景提示词；None 时现场生成
            （见 ``scene_visual_prompt``）。
        anchor_image_b64: 可选参考图（base64 PNG）。给了就跳过 wide 的
            txt2img，直接以它为锚点派生 closeup / mood。
        seed: 随机种子（仅本地后端生效）。
        size: "宽*高"，如 "1280*720"；None 时用部署默认的场景尺寸。
        max_retries: 每个视角的失败重试次数。
    输出:
        dict，{"wide": b64|None, "closeup": b64|None, "mood": b64|None}。
        wide 失败时 closeup / mood 一并跳过（无锚点）。
    副作用:
        调用图像生成后端（本地 GPU 或云端 API）；不写磁盘。
    模型:
        本地 Z-Image/SDXL（GPU）或云端 DashScope，取决于部署 settings。
    """
    from app.services.scene_generator import generate_scene_keyframes

    sc = Scene.from_dict(scene)
    return await generate_scene_keyframes(
        sc,
        visual_prompt,
        anchor_image=anchor_image_b64,
        seed=seed,
        max_retries=max_retries,
        size=size,
    )


async def character_three_view(
    character: dict,
    visual_prompt: Optional[str] = None,
    reference_image_b64: Optional[str] = None,
    seed: Optional[int] = None,
    size: Optional[str] = None,
    max_retries: int = 2,
) -> dict:
    """生成人物三视图：front / side / back（绿幕底，供后续抠像）。

    输入:
        character: 角色 dict（``extract_characters`` 的输出项）。
        visual_prompt: 英文角色提示词；None 时现场生成
            （见 ``character_visual_prompt``）。
        reference_image_b64: 可选参考图（base64 PNG）。给了就把它当
            front 锚点，只生成 side / back。
        seed: 随机种子（仅本地后端生效）。
        size: "宽*高"，如 "720*1280"；None 时用部署默认的人物尺寸。
        max_retries: 每个视角的失败重试次数。
    输出:
        dict，{"front": b64|None, "side": b64|None, "back": b64|None}。
    副作用:
        调用图像生成后端（本地 GPU 或云端 API）；不写磁盘。
        重试全部失败时底层抛 RuntimeError。
    模型:
        本地 Z-Image/SDXL（GPU）或云端 DashScope，取决于部署 settings。
    """
    from app.services.character_generator import generate_character_three_view

    char = Character.from_dict(character)
    return await generate_character_three_view(
        char,
        visual_prompt,
        reference_image=reference_image_b64,
        seed=seed,
        max_retries=max_retries,
        size=size,
    )


async def character_variation(
    character: dict,
    variation_prompt: str,
    reference_image_b64: Optional[str] = None,
    size: Optional[str] = None,
) -> Optional[str]:
    """生成人物换装/变体图。

    输入:
        character: 角色 dict（保留字段一致性，当前底层只用提示词）。
        variation_prompt: 变体的完整英文提示词。
        reference_image_b64: 可选风格参考图（base64 PNG）。
        size: "宽*高"；None 时用部署默认的人物尺寸。
    输出:
        base64 PNG 字符串；失败返回 None。
    副作用:
        调用图像生成后端（本地 GPU 或云端 API）；不写磁盘。
    模型:
        本地 Z-Image/SDXL（GPU）或云端 DashScope，取决于部署 settings。
    """
    from app.services.character_generator import generate_character_variation

    char = Character.from_dict(character)
    return await generate_character_variation(
        char,
        variation_prompt,
        reference_image_b64,
        size=size,
    )
