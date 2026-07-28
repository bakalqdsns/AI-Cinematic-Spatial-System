"""
Local Image Generator — Z-Image-Turbo (primary) / SDXL (fallback)

Provides text-to-image and image-to-image generation using local Diffusers
pipelines. No API key required — all inference runs locally on GPU.

The active pipeline is selected from ``image_model_id``:

  * ``Tongyi-MAI/Z-Image-Turbo`` (primary, default) → ZImagePipeline +
    ZImageImg2ImgPipeline. Uses distilled inference defaults
    (num_inference_steps=9, guidance_scale=0.0).
  * anything else containing ``z-image`` / ``z_image`` → same Z-Image path.
  * ``stabilityai/stable-diffusion-xl-base-1.0`` (fallback) → SDXL with the
    classic 25 steps / CFG 7.5 defaults.

Inpainting currently only supports SDXL. Calling
``generate_inpaint()`` on a Z-Image generator logs a warning and returns
``None``; the caller's fallback chain (LaMa in ``inpaint_utils``) takes over.
A Z-Image inpaint pipeline will be wired in once diffusers ships one.

Usage:
    generator = LocalImageGenerator()
    image = generator.generate("a beautiful woman, cinematic lighting")
    b64 = generator.pil_to_base64(image)
"""
from __future__ import annotations

import base64
import gc
import io
import logging
import os
import signal
import sys
import traceback
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# Enable Python's faulthandler so that if a native crash (CUDA OOM kill,
# segfault inside a C extension, etc.) kills the process, we still get a
# useful traceback in stderr / the rotating log file.  Without this a
# `torch.cuda.OutOfMemoryError` or a `RuntimeError: CUDA error: out of memory`
# that's raised from native code often kills the process silently — making
# "the backend timed out" the only symptom the user sees.
try:
    import faulthandler

    faulthandler.enable()
    # Dump tracebacks on SIGUSR1 (handy for live debugging).  Windows
    # doesn't have SIGUSR1 — skip silently there.
    try:
        faulthandler.register(signal.SIGUSR1)
    except (AttributeError, ValueError):
        pass
    logger.info("[ImageGen] faulthandler enabled — native crashes will dump traceback")
except Exception as _e:
    logger.warning("[ImageGen] faulthandler not enabled: %s", _e)


# ── Device selection ─────────────────────────────────────────────────────────────

def _get_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


# ── Pipeline routing ────────────────────────────────────────────────────────────

# Defaults for each supported pipeline family. Z-Image-Turbo is distilled —
# high CFG or many steps actually degrade output.
_GEN_DEFAULTS: dict[str, dict[str, float]] = {
    "z_image": {"steps": 9,  "guidance_scale": 0.0},
    "sdxl":    {"steps": 25, "guidance_scale": 7.5},
}


def _detect_pipeline_type(model_id: str) -> str:
    """Map a HuggingFace repo id to one of our supported pipeline types."""
    mid = (model_id or "").lower()
    if "z-image" in mid or "z_image" in mid:
        return "z_image"
    return "sdxl"


def _round_to_multiple(value: int, multiple: int = 16) -> int:
    """Round dimensions up to the nearest legal size (Z-Image requires /16)."""
    if value <= 0:
        return multiple
    return max(multiple, ((value + multiple - 1) // multiple) * multiple)


def _gpu_vram_gb() -> tuple[float, float]:
    """Return (free, total) VRAM in GB; (0, 0) when CUDA is unavailable."""
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info(0)
            return free / 1024 ** 3, total / 1024 ** 3
    except Exception:
        pass
    return 0.0, 0.0


def _clear_cuda_cache_best_effort() -> None:
    """
    Free as much GPU memory as possible without touching the model manager.

    Called on every error path (load, warmup, inference) so a failed
    request doesn't leave the GPU holding onto stale tensors.  Without
    this a half-loaded pipeline can keep ~14 GB reserved across requests.
    """
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
    except Exception as e:
        logger.warning("[ImageGen] _clear_cuda_cache_best_effort failed: %s", e)


# ── Pipeline loader ─────────────────────────────────────────────────────────────

def _load_pipeline(
    model_id: str,
    dtype_name: str,
    pipeline_type: str,
    checkpoint_dir: str = None,
) -> Optional["DiffusionPipeline"]:
    """
    Load the appropriate Diffusers pipeline for the requested model_id.

    ``pipeline_type`` must come from :func:`_detect_pipeline_type`. On any
    failure we fall back to SDXL so the application stays usable.

    For Z-Image we first run ``ZImageLoader.ensure_downloaded()`` so the
    ~33 GB snapshot is already on disk (HF Hub Xet-disabled → ModelScope
    fallback).  We then pass the *local snapshot path* to
    ``from_pretrained`` instead of the repo id, which keeps the pipeline
    loading fully offline and lets it pick up files exactly where the
    loader left them.
    """
    import time as _time

    # Capture a VRAM snapshot before we touch anything so failures are
    # diagnosable.  If the user reports "backend timed out", the
    # free/total numbers will tell us whether we died of OOM, a CUDA
    # error, or just a missing file.
    try:
        import torch
        if torch.cuda.is_available():
            _free, _total = torch.cuda.mem_get_info(0)
            logger.info(
                "[ImageGen] _load_pipeline start: model=%s type=%s vram=%.2f/%.2fGB",
                model_id, pipeline_type,
                _free / 1024 ** 3, _total / 1024 ** 3,
            )
        else:
            logger.info(
                "[ImageGen] _load_pipeline start: model=%s type=%s vram=<cpu only>",
                model_id, pipeline_type,
            )
    except Exception:
        pass

    try:
        from diffusers import DiffusionPipeline

        dtype_map = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        dtype = dtype_map.get(dtype_name, torch.bfloat16)
        device = _get_device()

        if pipeline_type == "z_image":
            # Prefer ZImagePipeline; fall back to the generic DiffusionPipeline
            # in case the upstream class name has drifted.
            try:
                from diffusers import ZImagePipeline  # type: ignore[attr-defined]
                pipe_cls = ZImagePipeline
            except Exception as e:
                logger.warning(
                    "[ImageGen] ZImagePipeline not available in this diffusers build; "
                    "using DiffusionPipeline.from_pretrained() for %s: %s",
                    model_id, e,
                )
                pipe_cls = DiffusionPipeline
            logger.info("[ImageGen] Loading Z-Image model %s on %s (dtype=%s)…", model_id, device, dtype_name)

            # Ensure the snapshot is local first — from_pretrained() then
            # only reads files, never hits the network.  We pull
            # ``checkpoint_dir`` from settings if the caller didn't provide
            # one (which is the common path).
            if not checkpoint_dir:
                try:
                    from app.config import settings as _settings
                    checkpoint_dir = str(_settings.image_checkpoint_dir)
                except Exception:
                    pass
            load_path = model_id  # default: trust hub_layout resolution
            if checkpoint_dir:
                try:
                    from app.models.z_image_loader import ZImageModel
                    loader = ZImageModel(model_id=model_id, checkpoint_dir=checkpoint_dir)
                    local_path = loader.ensure_downloaded()
                    if local_path:
                        load_path = local_path
                        logger.info("[ImageGen] Loading Z-Image from local snapshot: %s", local_path)
                except Exception as e:
                    # Surface, but don't fail outright — from_pretrained may
                    # still succeed via its own network dance if the user
                    # has HF_ENDPOINT reachable directly.
                    logger.warning("[ImageGen] Local snapshot pre-stage failed, falling back to from_pretrained: %s", e)
        else:
            try:
                from diffusers import StableDiffusionXLPipeline
                pipe_cls = StableDiffusionXLPipeline
            except Exception:
                pipe_cls = DiffusionPipeline
            logger.info("[ImageGen] Loading SDXL %s on %s (dtype=%s)…", model_id, device, dtype_name)

        _t0 = _time.time()
        try:
            pipe = pipe_cls.from_pretrained(
                load_path,
                torch_dtype=dtype,
                use_safetensors=False,
                variant="fp16" if dtype == torch.float16 else None,
            )
        except Exception as e:
            logger.exception(
                "[ImageGen] from_pretrained FAILED for %s (load_path=%s): %s",
                model_id, load_path, e,
            )
            _clear_cuda_cache_best_effort()
            raise
        logger.info("[ImageGen] from_pretrained done in %.1fs", _time.time() - _t0)

        try:
            _t1 = _time.time()
            pipe.to(device)
            logger.info(
                "[ImageGen] pipe.to(%s) done in %.1fs; vram_after=%.2f/%.2fGB",
                device, _time.time() - _t1,
                *(_gpu_vram_gb() if torch.cuda.is_available() else (0.0, 0.0)),
            )
        except Exception as e:
            logger.exception(
                "[ImageGen] pipe.to(%s) FAILED for %s: %s",
                device, model_id, e,
            )
            _clear_cuda_cache_best_effort()
            raise

        logger.info("[ImageGen] Pipeline ready: %s", model_id)
        return pipe
    except Exception as e:
        logger.warning(
            "[ImageGen] Failed to load %s (type=%s): %s — falling back to SDXL",
            model_id, pipeline_type, e,
        )
        _clear_cuda_cache_best_effort()
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
            device = _get_device()
            pipe = StableDiffusionXLPipeline.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                torch_dtype=torch.bfloat16,
                use_safetensors=False,
            )
            pipe.to(device)
            logger.info("[ImageGen] SDXL fallback ready")
            return pipe
        except Exception as e2:
            logger.exception(
                "[ImageGen] SDXL fallback also failed for %s: %s",
                model_id, e2,
            )
            _clear_cuda_cache_best_effort()
            return None


def _load_img2img_pipeline(
    model_id: str,
    dtype_name: str,
    pipeline_type: str,
    checkpoint_dir: str = None,
) -> Optional["DiffusionPipeline"]:
    """Lazy-load a separate img2img pipeline (kept distinct from the txt2img one).

    For Z-Image we again pre-stage the snapshot via ``ZImageModel`` and
    point ``from_pretrained`` at the local path so the pipeline loader
    never makes a network call.
    """
    import time as _time
    try:
        import torch
        dtype_map = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        dtype = dtype_map.get(dtype_name, torch.bfloat16)
        device = _get_device()

        load_path = model_id

        if pipeline_type == "z_image":
            try:
                from diffusers import ZImageImg2ImgPipeline  # type: ignore[attr-defined]
                pipe_cls = ZImageImg2ImgPipeline
            except Exception as e:
                logger.warning(
                    "[ImageGen] ZImageImg2ImgPipeline not available; "
                    "cannot run img2img on Z-Image model %s: %s",
                    model_id, e,
                )
                return None
            logger.info("[ImageGen] Loading Z-Image img2img %s…", model_id)
            if not checkpoint_dir:
                try:
                    from app.config import settings as _settings
                    checkpoint_dir = str(_settings.image_checkpoint_dir)
                except Exception:
                    pass
            if checkpoint_dir:
                try:
                    from app.models.z_image_loader import ZImageModel
                    loader = ZImageModel(model_id=model_id, checkpoint_dir=checkpoint_dir)
                    local_path = loader.ensure_downloaded()
                    if local_path:
                        load_path = local_path
                except Exception as e:
                    logger.warning("[ImageGen] Local snapshot pre-stage failed for img2img: %s", e)
        else:
            from diffusers import StableDiffusionImg2ImgPipeline
            pipe_cls = StableDiffusionImg2ImgPipeline
            logger.info("[ImageGen] Loading SDXL img2img %s…", model_id)

        _t0 = _time.time()
        try:
            pipe = pipe_cls.from_pretrained(
                load_path,
                torch_dtype=dtype,
                use_safetensors=False,
                variant="fp16" if dtype == torch.float16 else None,
            )
        except Exception as e:
            logger.exception(
                "[ImageGen] img2img from_pretrained FAILED for %s: %s", model_id, e,
            )
            _clear_cuda_cache_best_effort()
            raise

        _t1 = _time.time()
        try:
            pipe.to(device)
        except Exception as e:
            logger.exception(
                "[ImageGen] img2img pipe.to(%s) FAILED for %s: %s", device, model_id, e,
            )
            _clear_cuda_cache_best_effort()
            raise

        logger.info(
            "[ImageGen] img2img ready for %s in %.1fs (load=%.1fs); vram_after=%.2f/%.2fGB",
            model_id, _time.time() - _t0, _t1 - _t0,
            *_gpu_vram_gb(),
        )
        return pipe
    except Exception as e:
        logger.warning("[ImageGen] img2img load failed for %s: %s", model_id, e)
        _clear_cuda_cache_best_effort()
        return None


# ── Type alias (lazy import) ─────────────────────────────────────────────────────

try:
    from diffusers import DiffusionPipeline
except ImportError:
    DiffusionPipeline = None  # type: ignore


# ── Generator class ─────────────────────────────────────────────────────────────

class LocalImageGenerator:
    """
    Local image generation using Diffusers pipelines.

    Supports:
      - Text-to-image (generate)
      - Image-to-image with a reference (generate_with_image)
      - Inpainting with a mask (generate_inpaint) — SDXL only

    All methods return PIL.Image or None on failure.
    Use pil_to_base64() to serialize to a raw base64 string (no data URL prefix).
    """

    DEFAULT_MODEL_ID = "Tongyi-MAI/Z-Image-Turbo"
    DEFAULT_SIZE = (1024, 1024)

    def __init__(
        self,
        model_id: str = None,
        dtype_name: str = "bfloat16",
        enable_attention_slicing: bool = True,
        enable_vae_slicing: bool = True,
        checkpoint_dir: str = None,
    ):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.dtype_name = dtype_name
        self._pipeline_type: str = _detect_pipeline_type(self.model_id)
        self._pipe: Optional[DiffusionPipeline] = None
        self._img2img_pipe: Optional[DiffusionPipeline] = None
        self._enable_attention_slicing = enable_attention_slicing
        self._enable_vae_slicing = enable_vae_slicing
        # Optional override for the Z-Image / SDXL cache root.  When set,
        # the loaders call ``ZImageModel.ensure_downloaded`` against this
        # directory before ``from_pretrained`` so all weights live there.
        self._checkpoint_dir = checkpoint_dir

    # ── Lazy loading ─────────────────────────────────────────────────────────

    def _ensure_pipe(self) -> Optional[DiffusionPipeline]:
        if self._pipe is None:
            logger.info(
                "[ImageGen] _ensure_pipe: loading %s (type=%s dtype=%s)",
                self.model_id, self._pipeline_type, self.dtype_name,
            )
            try:
                self._pipe = _load_pipeline(
                    self.model_id,
                    self.dtype_name,
                    self._pipeline_type,
                    checkpoint_dir=self._checkpoint_dir,
                )
            except Exception as e:
                logger.exception(
                    "[ImageGen] _ensure_pipe: _load_pipeline raised for %s: %s",
                    self.model_id, e,
                )
                self._pipe = None
                _clear_cuda_cache_best_effort()
                return None
            if self._pipe is not None:
                if self._enable_attention_slicing:
                    try:
                        self._pipe.enable_attention_slicing()
                    except Exception:
                        pass  # some pipelines (e.g. Z-Image) don't expose this
                if self._enable_vae_slicing:
                    try:
                        self._pipe.enable_vae_slicing()
                    except Exception:
                        pass
                logger.info(
                    "[ImageGen] _ensure_pipe: pipeline ready for %s; vram=%.2f/%.2fGB",
                    self.model_id, *_gpu_vram_gb(),
                )
            else:
                logger.error(
                    "[ImageGen] _ensure_pipe: pipeline still None after load — SDXL fallback also failed",
                )
                _clear_cuda_cache_best_effort()
        return self._pipe

    def _ensure_img2img_pipe(self) -> Optional[DiffusionPipeline]:
        if self._img2img_pipe is None:
            logger.info(
                "[ImageGen] _ensure_img2img_pipe: loading %s (type=%s)",
                self.model_id, self._pipeline_type,
            )
            try:
                self._img2img_pipe = _load_img2img_pipeline(
                    self.model_id,
                    self.dtype_name,
                    self._pipeline_type,
                    checkpoint_dir=self._checkpoint_dir,
                )
            except Exception as e:
                logger.exception(
                    "[ImageGen] _ensure_img2img_pipe: load raised for %s: %s",
                    self.model_id, e,
                )
                self._img2img_pipe = None
                _clear_cuda_cache_best_effort()
        return self._img2img_pipe

    def unload(self) -> None:
        """Release GPU memory held by the pipelines."""
        logger.info(
            "[ImageGen] unload() called; vram_before=%.2f/%.2fGB",
            *_gpu_vram_gb(),
        )
        if self._pipe is not None:
            try:
                del self._pipe
            except Exception:
                pass
            self._pipe = None
        if self._img2img_pipe is not None:
            try:
                del self._img2img_pipe
            except Exception:
                pass
            self._img2img_pipe = None
        # Force a real release — drop Python refs + run the GC + clear CUDA
        # allocator cache.  Without this, ``del`` only drops the local
        # binding but the tensors stay pinned in PyTorch's caching
        # allocator for up to several seconds.
        gc.collect()
        _clear_cuda_cache_best_effort()
        logger.info(
            "[ImageGen] unload() done; vram_after=%.2f/%.2fGB",
            *_gpu_vram_gb(),
        )

    # ── Generation methods ───────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: tuple[int, int] = None,
        steps: int = None,
        guidance_scale: float = None,
        seed: Optional[int] = None,
    ) -> Optional[Image.Image]:
        """
        Text-to-image generation.

        ``steps`` / ``guidance_scale`` default to values appropriate for the
        active pipeline family (Z-Image-Turbo: 9 / 0.0; SDXL: 25 / 7.5).
        Pass explicit values to override.
        """
        try:
            pipe = self._ensure_pipe()
        except Exception as e:
            logger.exception(
                "[ImageGen] generate: pipeline load failed: %s", e,
            )
            _clear_cuda_cache_best_effort()
            return None
        if pipe is None:
            logger.warning("[ImageGen] generate: no pipeline available for %s", self.model_id)
            return None

        defaults = _GEN_DEFAULTS.get(self._pipeline_type, _GEN_DEFAULTS["sdxl"])
        steps = steps if steps is not None else defaults["steps"]
        guidance_scale = guidance_scale if guidance_scale is not None else defaults["guidance_scale"]

        width, height = size or self.DEFAULT_SIZE
        # Z-Image (and most SDXL checkpoints) require dimensions divisible by 16.
        width = _round_to_multiple(width, 16)
        height = _round_to_multiple(height, 16)

        gen_kwargs: dict = {
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
        }
        if seed is not None:
            import torch
            gen_kwargs["generator"] = torch.Generator(device=_get_device()).manual_seed(seed)

        logger.info(
            "[ImageGen] generate: model=%s size=%dx%d steps=%d cfg=%.2f seed=%s vram=%.2f/%.2fGB",
            self.model_id, width, height, steps, guidance_scale, seed,
            *_gpu_vram_gb(),
        )
        try:
            result = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                width=width,
                height=height,
                **gen_kwargs,
            )
            image = result.images[0] if hasattr(result, "images") else result[0]
            logger.info(
                "[ImageGen] generate: success; vram_after=%.2f/%.2fGB",
                *_gpu_vram_gb(),
            )
            return image
        except Exception as e:
            logger.exception(
                "[ImageGen] generate failed (model=%s size=%dx%d steps=%d): %s",
                self.model_id, width, height, steps, e,
            )
            # Critical: a CUDA OOM here would otherwise leave the
            # pipeline's KV-cache pinned.  Empty the cache so the next
            # request starts with a clean allocator.
            _clear_cuda_cache_best_effort()
            return None

    def generate_with_image(
        self,
        prompt: str,
        reference_image: Image.Image | str,
        strength: float = 0.6,
        steps: int = None,
        guidance_scale: float = None,
    ) -> Optional[Image.Image]:
        """
        Image-to-image generation (style/content consistency).

        Dispatches to ZImageImg2ImgPipeline or StableDiffusionImg2ImgPipeline
        depending on the active model.
        """
        # Accept base64 input
        if isinstance(reference_image, str):
            reference_image = self._base64_to_pil(reference_image)
        if reference_image is None:
            return None

        defaults = _GEN_DEFAULTS.get(self._pipeline_type, _GEN_DEFAULTS["sdxl"])
        steps = steps if steps is not None else defaults["steps"]
        guidance_scale = guidance_scale if guidance_scale is not None else defaults["guidance_scale"]

        try:
            img_pipe = self._ensure_img2img_pipe()
            if img_pipe is None:
                # Couldn't load an img2img-specific pipe. If we're on SDXL,
                # the txt2img pipe *is* an SDXLPipeline and img2img is not
                # supported there, so we surface the failure. For Z-Image
                # without the dedicated class there's nothing we can do.
                logger.warning("[ImageGen] no img2img pipeline available for %s", self.model_id)
                return None

            logger.info(
                "[ImageGen] generate_with_image: model=%s strength=%.2f steps=%d cfg=%.2f vram=%.2f/%.2fGB",
                self.model_id, strength, steps, guidance_scale, *_gpu_vram_gb(),
            )
            result = img_pipe(
                prompt=prompt,
                image=reference_image,
                strength=strength,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
            )
            return result.images[0] if hasattr(result, "images") else result[0]
        except Exception as e:
            logger.exception(
                "[ImageGen] generate_with_image failed (model=%s strength=%.2f): %s",
                self.model_id, strength, e,
            )
            _clear_cuda_cache_best_effort()
            return None

    def generate_inpaint(
        self,
        prompt: str,
        reference_image: Image.Image | str,
        mask_image: Image.Image,
        steps: int = 25,
        guidance_scale: float = 7.5,
    ) -> Optional[Image.Image]:
        """
        Inpainting — fill masked regions of an image.

        Only SDXL is currently supported. On Z-Image we log a warning and
        return ``None``; the upstream caller (inpaint_utils) will fall back
        to LaMa.
        """
        if self._pipeline_type == "z_image":
            logger.warning(
                "[ImageGen] inpainting is not supported on Z-Image yet; "
                "caller should fall back to LaMa."
            )
            return None

        try:
            pipe = self._ensure_pipe()
        except Exception as e:
            logger.exception("[ImageGen] inpaint: pipeline load failed: %s", e)
            _clear_cuda_cache_best_effort()
            return None
        if pipe is None:
            return None

        if isinstance(reference_image, str):
            reference_image = self._base64_to_pil(reference_image)
        if reference_image is None:
            return None

        try:
            from diffusers import StableDiffusionInpaintPipeline
            result = pipe(
                prompt=prompt,
                image=reference_image,
                mask_image=mask_image,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
            )
            return result.images[0] if hasattr(result, "images") else result[0]
        except Exception as e:
            logger.exception("[ImageGen] generate_inpaint failed: %s", e)
            _clear_cuda_cache_best_effort()
            return None

    # ── Serialization ────────────────────────────────────────────────────────

    @staticmethod
    def pil_to_base64(image: Image.Image, format: str = "PNG") -> Optional[str]:
        """Convert PIL Image to a base64-encoded string (no data URL prefix).

        The frontend prepends ``data:image/png;base64,`` itself, so we keep
        this function returning the raw base64 to avoid double prefixing.
        """
        if image is None:
            return None
        try:
            buf = io.BytesIO()
            image.save(buf, format=format)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            logger.warning("[ImageGen] pil_to_base64 failed: %s", e)
            return None

    @staticmethod
    def _base64_to_pil(b64: str) -> Optional[Image.Image]:
        """Decode a base64 data URL to PIL Image."""
        try:
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            data = base64.b64decode(b64)
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as e:
            logger.warning("[ImageGen] _base64_to_pil failed: %s", e)
            return None

    @staticmethod
    def save_image(image: Image.Image, path: str | Path) -> bool:
        """Save PIL Image to a local file."""
        try:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path)
            return True
        except Exception as e:
            logger.warning("[ImageGen] save_image failed: %s", e)
            return False


# ── Module-level singleton ───────────────────────────────────────────────────────

import threading as _threading

_img_gen: Optional[LocalImageGenerator] = None
_img_gen_lock = _threading.Lock()


def _default_checkpoint_dir() -> Optional[str]:
    """Return the project-wide image_checkpoint_dir, or None if settings unimportable."""
    try:
        from app.config import settings as _settings
        return str(_settings.image_checkpoint_dir)
    except Exception:
        return None


def get_image_generator() -> LocalImageGenerator:
    """Return the shared LocalImageGenerator singleton (loads lazily on first call)."""
    global _img_gen
    # Use a lock so two concurrent requests can't both try to build the
    # pipeline at the same time and double the GPU memory peak.  The
    # lock is only held during object construction — once the singleton
    # exists, subsequent calls return immediately.
    if _img_gen is None:
        with _img_gen_lock:
            if _img_gen is None:
                logger.info(
                    "[ImageGen] get_image_generator: first call, building singleton (model=%s dtype=%s)",
                    settings.image_model_id if False else "from-defaults",
                    "from-defaults",
                )
                _img_gen = LocalImageGenerator(checkpoint_dir=_default_checkpoint_dir())
    return _img_gen


def configure_image_generator(model_id: str, dtype_name: str) -> None:
    """Reconfigure the shared generator (e.g. from Settings).

    Resets the singleton so the next ``get_image_generator()`` call returns
    a generator bound to the new model.

    If a previous generator is resident in GPU memory, we unload it first so
    the new model doesn't pile up on top of the old one (the Z-Image-Turbo
    pipeline is ~14 GB on its own — stacking two of them kills an RTX 4060 Ti).
    """
    global _img_gen
    with _img_gen_lock:
        if _img_gen is not None:
            try:
                _img_gen.unload()
            except Exception as e:
                logger.warning("[ImageGen] configure: unload old generator failed: %s", e)
            _img_gen = None
            _clear_cuda_cache_best_effort()
        _img_gen = LocalImageGenerator(
            model_id=model_id,
            dtype_name=dtype_name,
            checkpoint_dir=_default_checkpoint_dir(),
        )
    logger.info("[ImageGen] Configured: model_id=%s dtype=%s", model_id, dtype_name)


def warmup_image_generator(model_id: str, dtype_name: str) -> bool:
    """
    Trigger eager download + load of the image model weights.
    Call this during startup (lifespan) when lazy_load=False so the first
    generation request doesn't pay the ~33 GB download cost.

    For Z-Image-Turbo, this delegates the heavy lifting to
    ``ZImageModel.ensure_downloaded()`` (HF Hub with Xet disabled, then
    ModelScope mirror fallback).  Only after the snapshot is on disk do
    we instantiate the pipeline — so the warmup is a clean two-phase
    process: download network → load GPU.

    Returns True on success, False on failure (download/load failed).
    Any exception during warmup is caught, logged, and swallowed so the
    server can keep serving requests while the user investigates.
    """
    try:
        logger.info(
            "[ImageGen] Warmup: preparing %s (this happens once)… vram=%.2f/%.2fGB",
            model_id, *_gpu_vram_gb(),
        )

        # Phase 1 — disk pre-stage via ZImageModel.  For non-Z-Image model
        # ids (e.g. SDXL) the loader is a no-op and we proceed straight
        # to Phase 2 (diffusers' own from_pretrained).
        ckpt_dir = _default_checkpoint_dir()
        gen = LocalImageGenerator(
            model_id=model_id,
            dtype_name=dtype_name,
            checkpoint_dir=ckpt_dir,
        )

        try:
            pipe = gen._ensure_pipe()
        except Exception as e:
            logger.exception("[ImageGen] Warmup: _ensure_pipe raised: %s", e)
            _clear_cuda_cache_best_effort()
            return False

        if pipe is None:
            logger.warning("[ImageGen] Warmup: _ensure_pipe returned None — model will load on first use")
            _clear_cuda_cache_best_effort()
            return False
        logger.info(
            "[ImageGen] Warmup: %s ready; vram=%.2f/%.2fGB",
            model_id, *_gpu_vram_gb(),
        )
        # Stash as singleton so subsequent get_image_generator() calls reuse it.
        global _img_gen
        with _img_gen_lock:
            if _img_gen is not None:
                try:
                    _img_gen.unload()
                except Exception:
                    pass
            _img_gen = gen
        return True
    except Exception as e:
        logger.exception(
            "[ImageGen] Warmup failed for %s: %s — models will load on first use",
            model_id, e,
        )
        _clear_cuda_cache_best_effort()
        return False