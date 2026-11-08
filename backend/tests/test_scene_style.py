"""纸雕 HD-2D 统一风格测试（不加载真实模型、不触网、不调 ComfyUI）。

覆盖：
- apply_scene_style / apply_character_style 幂等；
- 场景出图四条通路（zimage_lora / comfyui / diffusers / 云端）都带统一风格后缀；
- 人物提示词：绿幕条款一字不动且在最后，纸雕风格词只在人物描述部分。
"""
import asyncio
import base64
import io

from PIL import Image

from app.services import (
    character_generator,
    comfyui_client,
    image_generator,
    scene_generator,
    settings_manager,
    zimage_lora_client,
)
from app.services.scene_style import (
    CHARACTER_STYLE_SUFFIX,
    SCENE_NEGATIVE_PROMPT,
    SCENE_STYLE_SUFFIX,
    apply_character_style,
    apply_scene_style,
)


# ── Fakes ───────────────────────────────────────────────────────────────────────

class FakePipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return Image.new("RGB", (kwargs.get("width", 8), kwargs.get("height", 8)), (1, 2, 3))


class FakeDiffusersGenerator:
    def __init__(self):
        self.calls = []
        self.img2img_calls = []

    def generate(self, prompt, seed=None, size=None):
        self.calls.append({"prompt": prompt, "seed": seed, "size": size})
        return Image.new("RGB", (8, 8), (200, 100, 50))

    def generate_with_image(self, prompt, reference_image_b64, strength):
        self.img2img_calls.append({"prompt": prompt, "strength": strength})
        return Image.new("RGB", (8, 8), (50, 100, 200))

    @staticmethod
    def pil_to_base64(image):
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")


def _force_backend(monkeypatch, value):
    real_get = settings_manager.get

    def fake_get(key, default=None):
        if key == "local_image_backend":
            return value
        return real_get(key, default)

    monkeypatch.setattr(settings_manager, "get", fake_get)


# ── 幂等性 ─────────────────────────────────────────────────────────────────────

def test_apply_scene_style_appends_suffix_and_negative():
    styled, neg = apply_scene_style("a quiet campus at dusk")
    assert styled.startswith("a quiet campus at dusk")
    assert SCENE_STYLE_SUFFIX in styled
    assert neg == SCENE_NEGATIVE_PROMPT


def test_apply_scene_style_idempotent_on_own_output():
    styled, _ = apply_scene_style("a quiet campus at dusk")
    again, neg = apply_scene_style(styled)
    assert again == styled, "already-styled prompt must not be appended twice"
    assert again.count(SCENE_STYLE_SUFFIX) == 1
    assert neg == SCENE_NEGATIVE_PROMPT


def test_apply_scene_style_idempotent_on_marker():
    base = "a handcrafted paper diorama of a school campus"
    styled, _ = apply_scene_style(base)
    assert styled == base


def test_apply_character_style_idempotent():
    styled = apply_character_style("a girl in a navy uniform")
    assert CHARACTER_STYLE_SUFFIX in styled
    assert apply_character_style(styled) == styled


# ── 场景：四条通路都带统一风格 ─────────────────────────────────────────────────

def test_zimage_lora_backend_carries_unified_style(monkeypatch):
    _force_backend(monkeypatch, "zimage_lora")
    fake = FakePipeline()
    zimage_lora_client.set_pipeline_for_testing(fake)
    try:
        result = asyncio.run(
            scene_generator._generate_via_local("empty schoolyard at dusk", seed=5, size="1344*768")
        )
    finally:
        zimage_lora_client.reset_pipeline_for_testing()
    assert result
    kw = fake.calls[0]
    assert "empty schoolyard at dusk" in kw["prompt"]
    assert SCENE_STYLE_SUFFIX in kw["prompt"]
    assert kw["negative_prompt"] == SCENE_NEGATIVE_PROMPT


def test_comfyui_backend_carries_style_and_negative(monkeypatch):
    _force_backend(monkeypatch, "comfyui")
    monkeypatch.setattr(comfyui_client, "comfy_image_selected", lambda: True)
    captured = {}

    async def fake_gen(prompt, *, width, height, seed, negative=None):
        captured.update(prompt=prompt, negative=negative)
        return b"\x89PNG-fake"

    monkeypatch.setattr(comfyui_client, "generate_zimage_png", fake_gen)
    result = asyncio.run(
        scene_generator._generate_via_local("empty schoolyard at dusk", seed=5, size="640*360")
    )
    assert result == base64.b64encode(b"\x89PNG-fake").decode("ascii")
    assert "empty schoolyard at dusk" in captured["prompt"]
    assert SCENE_STYLE_SUFFIX in captured["prompt"]
    assert captured["negative"] == SCENE_NEGATIVE_PROMPT


def test_diffusers_backend_carries_style(monkeypatch):
    _force_backend(monkeypatch, "diffusers")
    monkeypatch.setattr(comfyui_client, "comfy_image_selected", lambda: False)
    fake = FakeDiffusersGenerator()
    monkeypatch.setattr(image_generator, "get_image_generator", lambda: fake)
    result = asyncio.run(
        scene_generator._generate_via_local("empty schoolyard at dusk", seed=5, size="640*360")
    )
    assert result
    assert SCENE_STYLE_SUFFIX in fake.calls[0]["prompt"]


def test_diffusers_img2img_reference_carries_style(monkeypatch):
    _force_backend(monkeypatch, "diffusers")
    monkeypatch.setattr(comfyui_client, "comfy_image_selected", lambda: False)
    fake = FakeDiffusersGenerator()
    monkeypatch.setattr(image_generator, "get_image_generator", lambda: fake)
    result = asyncio.run(
        scene_generator._generate_via_local_with_reference(
            "close-up of a paper tree", "QUJD", strength=0.7,
        )
    )
    assert result
    assert SCENE_STYLE_SUFFIX in fake.img2img_calls[0]["prompt"]


def test_cloud_backend_carries_style(monkeypatch):
    from app.providers import cloud_router

    captured = {}

    async def fake_cloud(prompt, size=None, n=1):
        captured.update(prompt=prompt, size=size, n=n)
        return ["https://example.invalid/scene.png"]

    monkeypatch.setattr(cloud_router, "cloud_generate_image", fake_cloud)
    png = b"\x89PNG" + b"0" * 16
    monkeypatch.setattr(scene_generator, "_fetch_url", lambda url: png)
    result = asyncio.run(scene_generator._generate_via_cloud("empty campus at dawn"))
    assert result == base64.b64encode(png).decode("ascii")
    assert "empty campus at dawn" in captured["prompt"]
    assert SCENE_STYLE_SUFFIX in captured["prompt"]


# ── 人物：风格在人物描述部分，绿幕条款保持最后 ─────────────────────────────────

_FIXED_GREENSCREEN_SUFFIX = (
    ", solid bright green (#00FF00) chroma key background, "
    "no other objects in background, flat lighting"
)


def test_comfy_character_prompt_style_before_greenscreen():
    from app.services.video_adapter import _FLAT_CYCLORAMA_CLAUSE

    out = character_generator._comfy_character_prompt("白衣少女，全身像")
    # 人物本体纸雕风格
    assert CHARACTER_STYLE_SUFFIX in out
    # 绿幕条款一字不动
    assert _FIXED_GREENSCREEN_SUFFIX in out
    assert _FLAT_CYCLORAMA_CLAUSE in out
    # 风格词在人物描述部分（绿幕之前），绿幕措辞保持最后
    assert out.index(CHARACTER_STYLE_SUFFIX) < out.index("solid bright green (#00FF00)")
    tail = out[out.index("solid bright green (#00FF00)"):]
    assert "paper-cut" not in tail
    assert "paper diorama" not in tail
    assert out.endswith("Do not recolor the clothes green.")


def test_three_view_prompts_style_in_character_part(monkeypatch):
    from app.services.script_parser import Character

    captured = []

    async def fake_txt2img(prompt, *, label, seed=None, max_retries=2, size=None):
        captured.append(prompt)
        return "QUJD"

    async def fake_img2img(prompt, anchor_b64, *, label, strength=0.7, max_retries=2):
        captured.append(prompt)
        return "REVG"

    monkeypatch.setattr(character_generator, "_generate_with_retry", fake_txt2img)
    monkeypatch.setattr(character_generator, "_img2img_with_retry", fake_img2img)

    character = Character(id="c1", name="林织夏", visual_prompt="a girl in a navy uniform")
    results = asyncio.run(character_generator.generate_character_three_view(character))
    assert results == {"front": "QUJD", "side": "REVG", "back": "REVG"}
    assert len(captured) == 3
    for prompt in captured:
        assert CHARACTER_STYLE_SUFFIX in prompt
        green_at = prompt.index("solid bright green (#00FF00)")
        assert prompt.index(CHARACTER_STYLE_SUFFIX) < green_at
        assert "paper-cut" not in prompt[green_at:]


def test_character_diffusers_backend_carries_style(monkeypatch):
    monkeypatch.setattr(comfyui_client, "comfy_image_selected", lambda: False)
    fake = FakeDiffusersGenerator()
    monkeypatch.setattr(image_generator, "get_image_generator", lambda: fake)
    result = asyncio.run(character_generator._generate_via_local("a girl", size="720*1280"))
    assert result
    assert CHARACTER_STYLE_SUFFIX in fake.calls[0]["prompt"]
