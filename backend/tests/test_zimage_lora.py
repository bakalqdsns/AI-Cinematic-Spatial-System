"""
Tests for the zimage_lora local image backend (scene images only).

All tests use a fake pipeline — no GPU, no diffsynth import, no access to
F:\\zimage-lora model weights.
"""
import asyncio
import base64
import io
import sys

import pytest
from PIL import Image

from app.services import scene_generator, zimage_lora_client
from app.services import settings_manager


# ── Fakes ───────────────────────────────────────────────────────────────────────

class FakePipeline:
    """Records call kwargs and returns a tiny PIL image."""

    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return Image.new("RGB", (kwargs.get("width", 8), kwargs.get("height", 8)), (10, 20, 30))


class FakeDiffusersGenerator:
    """Stands in for image_generator.LocalImageGenerator on the fallback path."""

    def __init__(self):
        self.calls = []

    def generate(self, prompt, seed=None, size=None):
        self.calls.append({"prompt": prompt, "seed": seed, "size": size})
        return Image.new("RGB", (8, 8), (200, 100, 50))

    @staticmethod
    def pil_to_base64(image):
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def fake_pipeline():
    pipe = FakePipeline()
    zimage_lora_client.set_pipeline_for_testing(pipe)
    yield pipe
    zimage_lora_client.reset_pipeline_for_testing()


def _force_backend(monkeypatch, value):
    """Force settings_manager.get('local_image_backend') to a fixed value."""
    real_get = settings_manager.get

    def fake_get(key, default=None):
        if key == "local_image_backend":
            return value
        return real_get(key, default)

    monkeypatch.setattr(settings_manager, "get", fake_get)


# ── client.generate parameter passthrough ───────────────────────────────────────

def test_generate_passes_parameters_to_pipeline(fake_pipeline):
    img = zimage_lora_client.generate(
        "a paper forest",
        zimage_lora_client.NEGATIVE_PROMPT,
        1344,
        768,
        1234,
        steps=32,
        cfg=4.0,
    )
    assert isinstance(img, Image.Image)
    assert len(fake_pipeline.calls) == 1
    kw = fake_pipeline.calls[0]
    assert kw["prompt"] == "a paper forest"
    assert kw["negative_prompt"] == zimage_lora_client.NEGATIVE_PROMPT
    assert kw["width"] == 1344 and kw["height"] == 768
    assert kw["seed"] == 1234
    assert kw["num_inference_steps"] == 32
    assert kw["cfg_scale"] == 4.0


# ── sys.path injection / error reporting ────────────────────────────────────────

def test_missing_diffsynth_dir_raises_runtime_error(monkeypatch, tmp_path):
    zimage_lora_client.reset_pipeline_for_testing()
    bogus = str(tmp_path / "no-such-diffsynth")
    real_get = settings_manager.get

    def fake_get(key, default=None):
        if key == "zimage_lora_diffsynth_dir":
            return bogus
        return real_get(key, default)

    monkeypatch.setattr(settings_manager, "get", fake_get)
    try:
        with pytest.raises(RuntimeError, match="zimage_lora_diffsynth_dir"):
            zimage_lora_client.get_pipeline()
    finally:
        zimage_lora_client.reset_pipeline_for_testing()
    assert bogus not in sys.path


# ── scene_generator routing ─────────────────────────────────────────────────────

def test_scene_generator_zimage_lora_appends_style_and_neg(monkeypatch, fake_pipeline):
    _force_backend(monkeypatch, "zimage_lora")
    result = asyncio.run(
        scene_generator._generate_via_local("a quiet classroom at dusk", seed=42, size="1344*768")
    )
    assert result, "zimage_lora path should return base64 PNG"
    # decode to confirm it's a real PNG
    Image.open(io.BytesIO(base64.b64decode(result))).verify()

    assert len(fake_pipeline.calls) == 1
    kw = fake_pipeline.calls[0]
    assert "a quiet classroom at dusk" in kw["prompt"]
    assert zimage_lora_client.STYLE_SUFFIX in kw["prompt"]
    assert kw["negative_prompt"] == zimage_lora_client.NEGATIVE_PROMPT
    assert kw["width"] == 1344 and kw["height"] == 768
    assert kw["seed"] == 42
    assert kw["num_inference_steps"] == 32
    assert kw["cfg_scale"] == 4.0


def test_scene_generator_zimage_lora_default_size(monkeypatch, fake_pipeline):
    """image_size_scene unset/empty → default 1344x768."""
    _force_backend(monkeypatch, "zimage_lora")
    monkeypatch.setattr(scene_generator, "_default_scene_size", lambda: "")
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "image_size_scene", "", raising=False)

    asyncio.run(scene_generator._generate_via_local("paper world", seed=7, size=None))
    kw = fake_pipeline.calls[0]
    assert (kw["width"], kw["height"]) == (1344, 768)


def _disable_comfy(monkeypatch):
    """Make sure the fallback lands on the diffusers path, never real ComfyUI."""
    from app.services import comfyui_client
    monkeypatch.setattr(comfyui_client, "comfy_image_selected", lambda: False)


def test_scene_generator_falls_back_when_zimage_lora_raises(monkeypatch):
    _force_backend(monkeypatch, "zimage_lora")
    _disable_comfy(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("[zimage_lora] simulated missing model files")

    monkeypatch.setattr(zimage_lora_client, "generate", boom)

    fake_gen = FakeDiffusersGenerator()
    from app.services import image_generator
    monkeypatch.setattr(image_generator, "get_image_generator", lambda: fake_gen)

    result = asyncio.run(
        scene_generator._generate_via_local("a quiet classroom at dusk", seed=42, size="640*360")
    )
    assert result, "fallback path should still return base64 PNG"
    assert len(fake_gen.calls) == 1
    call = fake_gen.calls[0]
    # 兜底通路同样带统一纸雕风格后缀（全系统场景风格统一，见 scene_style）。
    from app.services.scene_style import SCENE_STYLE_SUFFIX
    assert "a quiet classroom at dusk" in call["prompt"]
    assert SCENE_STYLE_SUFFIX in call["prompt"]
    assert call["size"] == (640, 360)


def test_diffusers_backend_unaffected(monkeypatch):
    """local_image_backend == 'diffusers' never touches the zimage_lora client."""
    _force_backend(monkeypatch, "diffusers")
    _disable_comfy(monkeypatch)

    def boom(*args, **kwargs):
        raise AssertionError("zimage_lora client must not be called")

    monkeypatch.setattr(zimage_lora_client, "generate", boom)

    fake_gen = FakeDiffusersGenerator()
    from app.services import image_generator
    monkeypatch.setattr(image_generator, "get_image_generator", lambda: fake_gen)

    result = asyncio.run(scene_generator._generate_via_local("paper world", seed=1, size="640*360"))
    assert result
    assert len(fake_gen.calls) == 1
