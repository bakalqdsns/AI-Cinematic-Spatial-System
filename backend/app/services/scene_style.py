"""全系统统一的场景/人物出图风格：手工纸雕 HD-2D（《纸间行》）。

风格基准图：``docs/style/paper-diorama-reference.jpg``（手工纸雕立体模型、
层叠剪纸、卡纸纹理、移轴微缩摄影感、暖金色斜阳、近实远虚）。

所有场景出图通路（comfyui / diffusers / zimage_lora / 云端）都必须经过
:func:`apply_scene_style`；人物出图经过 :func:`apply_character_style`
（人物本体同为纸雕，但绿幕条款由调用方保持最后，不被风格词污染）。

措辞源自 ``F:\\zimage-lora\\gen_zhijing_scenes.py`` 的 STYLE/NEG，按参考图微调。
"""
from __future__ import annotations

# ── 场景：纸雕 HD-2D ────────────────────────────────────────────────────────────

SCENE_STYLE_SUFFIX = (
    "handcrafted paper diorama, layered paper cutout art, construction paper texture, "
    "paper-crafted buildings, trees and distant mountains, "
    "miniature scale model photography, Octopath Traveler HD-2D style, tilt-shift lens, "
    "warm golden low-angle sunlight, soft cinematic lighting, "
    "strong depth of field, sharp near layers with softly blurred distant layers, "
    "wide shot, rich detail, masterpiece, best quality"
)

SCENE_NEGATIVE_PROMPT = (
    "flat 2d, cartoon network style, low resolution, blurry, noisy, watermark, text, signature, "
    "bad anatomy, deformed hands, extra limbs, realistic photograph, photorealistic, "
    "modern city, glass skyscraper, car, crowd, overexposed, washed out, dull colours"
)

# ── 人物：同一纸雕风格（仅人物本体；背景条款由调用方另加并保持最后） ─────────────

CHARACTER_STYLE_SUFFIX = (
    "papercraft layered paper-cut character, handcrafted paper diorama style, "
    "construction paper texture"
)

# 已带风格词的判断标记（小写匹配）。覆盖两条后缀及常见同义写法。
_STYLE_MARKERS = (
    "paper diorama",
    "paper-cut",
    "paper cutout",
    "papercraft",
)


def _already_styled(prompt: str) -> bool:
    low = (prompt or "").lower()
    return any(marker in low for marker in _STYLE_MARKERS)


def apply_scene_style(prompt: str) -> tuple[str, str]:
    """给场景提示词追加纸雕 HD-2D 风格后缀，返回 ``(styled_prompt, negative)``。

    幂等：提示词里已有风格关键词（如 "paper diorama"）时不重复追加，
    负面词始终返回统一常量。
    """
    base = (prompt or "").strip()
    if _already_styled(base):
        return base, SCENE_NEGATIVE_PROMPT
    return f"{base}, {SCENE_STYLE_SUFFIX}", SCENE_NEGATIVE_PROMPT


def apply_character_style(prompt: str) -> str:
    """给人物提示词的人物描述部分追加纸雕风格词（幂等）。

    只负责人物本体的风格；绿幕等背景条款由调用方在此之后追加，
    保证背景措辞永远在最后、不被风格词改写。
    """
    base = (prompt or "").strip()
    if _already_styled(base):
        return base
    return f"{base}, {CHARACTER_STYLE_SUFFIX}"
