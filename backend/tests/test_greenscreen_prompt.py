"""第 2 轮「绿幕平整」：动作视频和人物静帧的绿幕提示词必须锁死。

证据：``minimax_8bf9eb2d.mp4`` 背景是暗绿、地板是更深的绿条，说明旧措辞
（只有固定后缀）压不住模型自己加地板和阴影。收紧后的提示词必须明确：
背景是一块平整的 bright green #00FF00 cyclorama，地面和背景是同一块
绿色，不要阴影、不要渐变、不要任何其他颜色或物体。

只断言提示词文本，不跑任何生成链路。
"""

_FIXED_GREENSCREEN_SUFFIX = (
    ", solid bright green (#00FF00) chroma key background, "
    "no other objects in background, flat lighting"
)


def _assert_flat_greenscreen(out: str, base: str) -> None:
    assert base in out
    # 固定后缀结构保持不变
    assert _FIXED_GREENSCREEN_SUFFIX in out
    # 第 2 轮收紧的平整措辞
    low = out.lower()
    assert "cyclorama" in low
    assert "the floor is the same green as the background" in low
    assert "no shadows" in low
    assert "no gradient" in low
    assert "no other colors or objects" in low
    # 人物锁定：不把衣服染绿
    assert "Do not recolor the clothes green." in out


def test_comfy_greenscreen_prompt_forces_flat_cyclorama():
    from app.services.video_adapter import _comfy_greenscreen_prompt

    out = _comfy_greenscreen_prompt("白衣少女 walks forward")
    _assert_flat_greenscreen(out, "白衣少女 walks forward")


def test_comfy_character_prompt_forces_flat_cyclorama():
    from app.services.character_generator import _comfy_character_prompt

    out = _comfy_character_prompt("纸雕质感的白衣少女，全身像")
    _assert_flat_greenscreen(out, "纸雕质感的白衣少女，全身像")


def test_flat_cyclorama_clause_is_shared_between_prompts():
    """人物静帧和动作视频共用同一句平整绿幕措辞，避免两处漂移。"""
    from app.services.character_generator import _comfy_character_prompt
    from app.services.video_adapter import (
        _FLAT_CYCLORAMA_CLAUSE,
        _comfy_greenscreen_prompt,
    )

    assert _FLAT_CYCLORAMA_CLAUSE in _comfy_greenscreen_prompt("walk")
    assert _FLAT_CYCLORAMA_CLAUSE in _comfy_character_prompt("portrait")
