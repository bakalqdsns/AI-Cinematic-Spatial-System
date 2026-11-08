"""
Z-Image LoRA Local Client
=========================

Local scene-image backend driven by DiffSynth-Studio's ``ZImagePipeline``
(same setup as the standalone scripts ``F:\\zimage-lora\\gen_hd2d.py`` /
``gen_zhijing_scenes.py``), used when ``settings.local_image_backend ==
"zimage_lora"``.

Key facts mirrored from the scripts:

- DiffSynth-Studio is NOT installed into the backend venv; its repo checkout
  (``settings.zimage_lora_diffsynth_dir``) is appended to ``sys.path`` lazily
  on first use so ``diffsynth.pipelines.z_image`` becomes importable.
- Model shards live under ``settings.zimage_lora_model_dir``:
  ``transformer/`` and ``text_encoder/`` hold several ``*.safetensors``
  shards plus a ``*_merged.safetensors`` that must be EXCLUDED from the
  glob; ``vae/diffusion_pytorch_model.safetensors`` and ``tokenizer/`` are
  loaded directly.
- VRAM config targets a 16 GB card: offload/onload in bf16 on CPU,
  preparing/computation in bf16 on CUDA, ``vram_limit = free VRAM GB - 0.5``.
- Generation defaults: 32 steps, cfg 4, 1344x768 (16:9 landscape).

The pipeline is a lazy singleton. Tests can inject a fake pipeline via
``set_pipeline_for_testing()`` (or pass ``pipeline=`` to ``generate()``)
so no GPU / model weights / diffsynth import are touched.
"""
from __future__ import annotations

import glob
import logging
import os
import sys
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paper-diorama HD-2D style (《纸间行》), from gen_zhijing_scenes.py ──────────

STYLE_SUFFIX = (
    "handcrafted paper diorama, layered paper cutout art, construction paper texture, "
    "miniature scale model photography, Octopath Traveler HD-2D style, tilt-shift lens, "
    "strong depth of field with blurred foreground and background, soft cinematic lighting, "
    "wide shot, rich detail, masterpiece, best quality"
)

NEGATIVE_PROMPT = (
    "flat 2d, cartoon network style, low resolution, blurry, noisy, watermark, text, signature, "
    "bad anatomy, deformed hands, extra limbs, realistic photograph, modern city, car, crowd, "
    "overexposed, washed out, dull colours"
)

DEFAULT_MODEL_DIR = r"F:\zimage-lora\models\Z-Image"
DEFAULT_DIFFSYNTH_DIR = r"F:\zimage-lora\DiffSynth-Studio"

DEFAULT_STEPS = 32
DEFAULT_CFG = 4.0
DEFAULT_WIDTH = 1344
DEFAULT_HEIGHT = 768

# ── Lazy singleton pipeline ─────────────────────────────────────────────────────

_pipeline = None
_pipeline_lock = threading.Lock()


def set_pipeline_for_testing(pipeline) -> None:
    """Inject a pre-built (fake) pipeline, skipping all loading. For tests."""
    global _pipeline
    with _pipeline_lock:
        _pipeline = pipeline


def reset_pipeline_for_testing() -> None:
    """Drop the cached pipeline so the next call reloads. For tests."""
    global _pipeline
    with _pipeline_lock:
        _pipeline = None


def _get_setting(key: str, default):
    try:
        from app.services.settings_manager import get as get_setting
        return get_setting(key, default)
    except Exception:
        return default


def _model_dir() -> str:
    return str(_get_setting("zimage_lora_model_dir", DEFAULT_MODEL_DIR) or DEFAULT_MODEL_DIR)


def _diffsynth_dir() -> str:
    return str(_get_setting("zimage_lora_diffsynth_dir", DEFAULT_DIFFSYNTH_DIR) or DEFAULT_DIFFSYNTH_DIR)


def _ensure_diffsynth_importable() -> None:
    """Append the DiffSynth-Studio checkout to sys.path and import the pipeline."""
    diffsynth_dir = _diffsynth_dir()
    if not os.path.isdir(diffsynth_dir):
        raise RuntimeError(
            f"[zimage_lora] DiffSynth-Studio 目录不存在: {diffsynth_dir!r}。"
            "请克隆 https://github.com/modelscope/DiffSynth-Studio 到本地，"
            "并把 settings.zimage_lora_diffsynth_dir 指向该克隆根目录"
            "（其中应包含 diffsynth/ 包）。"
        )
    if diffsynth_dir not in sys.path:
        sys.path.insert(0, diffsynth_dir)
    try:
        import diffsynth.pipelines.z_image  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"[zimage_lora] 无法从 {diffsynth_dir!r} 导入 diffsynth.pipelines.z_image: {e}。"
            "请确认 zimage_lora_diffsynth_dir 指向 DiffSynth-Studio 仓库根目录，"
            "且该克隆的依赖（torch 等）已在 backend/.venv 中可用。"
        ) from e


def _shard_paths(subdir: str) -> list[str]:
    """Glob safetensors shards under model_dir/subdir, excluding '*merged*'."""
    model_dir = _model_dir()
    pattern = os.path.join(model_dir, subdir, "*.safetensors")
    shards = [
        f for f in sorted(glob.glob(pattern))
        if "merged" not in os.path.basename(f)
    ]
    if not shards:
        raise RuntimeError(
            f"[zimage_lora] 在 {os.path.join(model_dir, subdir)!r} 下找不到模型 shard "
            f"（排除 *merged* 后为空）。请确认 settings.zimage_lora_model_dir 指向 "
            f"Z-Image 模型目录（默认 {DEFAULT_MODEL_DIR}），且 {subdir}/ 内含分片的 "
            "*.safetensors 文件。"
        )
    return shards


def _load_pipeline():
    """Build the real ZImagePipeline. Requires torch + diffsynth + model files."""
    _ensure_diffsynth_importable()
    import torch
    from diffsynth.pipelines.z_image import ModelConfig, ZImagePipeline

    model_dir = _model_dir()
    vae_path = os.path.join(model_dir, "vae", "diffusion_pytorch_model.safetensors")
    tokenizer_path = os.path.join(model_dir, "tokenizer")
    for required in (vae_path, tokenizer_path):
        if not os.path.exists(required):
            raise RuntimeError(
                f"[zimage_lora] 模型文件缺失: {required!r}。"
                f"请确认 settings.zimage_lora_model_dir（当前 {model_dir!r}）下的 "
                "vae/diffusion_pytorch_model.safetensors 与 tokenizer/ 完整存在。"
            )

    vram_cfg = {
        "offload_dtype": torch.bfloat16,
        "offload_device": "cpu",
        "onload_dtype": torch.bfloat16,
        "onload_device": "cpu",
        "preparing_dtype": torch.bfloat16,
        "preparing_device": "cuda",
        "computation_dtype": torch.bfloat16,
        "computation_device": "cuda",
    }
    pipe = ZImagePipeline.from_pretrained(
        torch_dtype=torch.bfloat16,
        device="cuda",
        model_configs=[
            ModelConfig(path=_shard_paths("transformer"), **vram_cfg),
            ModelConfig(path=_shard_paths("text_encoder"), **vram_cfg),
            ModelConfig(path=vae_path, **vram_cfg),
        ],
        tokenizer_config=ModelConfig(path=tokenizer_path),
        vram_limit=torch.cuda.mem_get_info("cuda")[1] / (1024 ** 3) - 0.5,
    )
    logger.info("[zimage_lora] ZImagePipeline loaded from %s", model_dir)
    return pipe


def get_pipeline():
    """Return the lazy singleton pipeline, loading it on first use."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            _pipeline = _load_pipeline()
        return _pipeline


# ── Generation ──────────────────────────────────────────────────────────────────

def generate(
    prompt: str,
    negative_prompt: Optional[str] = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    seed: Optional[int] = None,
    steps: int = DEFAULT_STEPS,
    cfg: float = DEFAULT_CFG,
    *,
    pipeline=None,
):
    """
    Run one txt2img pass on the Z-Image pipeline. Synchronous; call from a
    worker thread (``asyncio.to_thread``) in async contexts.

    Returns a PIL.Image. ``pipeline=`` overrides the singleton (testing).
    """
    pipe = pipeline if pipeline is not None else get_pipeline()
    if seed is None:
        import random
        seed = random.randint(0, 2 ** 31 - 1)
    return pipe(
        prompt=prompt,
        negative_prompt=negative_prompt or "",
        seed=seed,
        rand_device="cuda",
        num_inference_steps=steps,
        cfg_scale=cfg,
        height=height,
        width=width,
    )
