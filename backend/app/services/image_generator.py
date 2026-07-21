"""
Local Image Generator — Tongyi-MAI/Z-Image (via Diffusers)

Provides text-to-image and image-to-image generation using local Diffusers pipelines.
No API key required — all inference runs locally on GPU.

Image size: 1024x1024 (square, matching original wanx-v1 dimensions).

Usage:
    generator = LocalImageGenerator()
    image = generator.generate("a beautiful woman, cinematic lighting")
    b64 = generator.pil_to_base64(image)
"""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# ── Device selection ─────────────────────────────────────────────────────────────

def _get_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


# ── Pipeline loader ─────────────────────────────────────────────────────────────

def _load_pipeline(
    model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
    dtype_name: str = "bfloat16",
) -> Optional["DiffusionPipeline"]:
    """
    Load a Diffusers pipeline with the specified dtype.

    Tries the requested model first; on failure falls back to SDXL.
    Returns None if neither can be loaded.
    """
    try:
        import torch
        from diffusers import DiffusionPipeline

        dtype_map = {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        dtype = dtype_map.get(dtype_name, torch.bfloat16)
        device = _get_device()

        logger.info("[ImageGen] Loading %s on %s (dtype=%s)...", model_id, device, dtype_name)
        pipe = DiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            use_safetensors=True,
            variant="fp16" if dtype == torch.float16 else None,
        )
        pipe.to(device)
        logger.info("[ImageGen] Pipeline ready: %s", model_id)
        return pipe
    except Exception as e:
        logger.warning("[ImageGen] Failed to load %s: %s — trying SDXL fallback", model_id, e)
        try:
            import torch
            from diffusers import StableDiffusionXLPipeline
            device = _get_device()
            pipe = StableDiffusionXLPipeline.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                torch_dtype=torch.bfloat16,
                use_safetensors=True,
            )
            pipe.to(device)
            logger.info("[ImageGen] SDXL fallback ready")
            return pipe
        except Exception as e2:
            logger.error("[ImageGen] SDXL fallback also failed: %s", e2)
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
      - Inpainting with a mask (generate_inpaint)

    All methods return PIL.Image or None on failure.
    Use pil_to_base64() to serialize to data URL.
    """

    # Default target model
    DEFAULT_MODEL_ID = "stabilityai/stable-diffusion-xl-base-1.0"
    DEFAULT_SIZE = (1024, 1024)

    def __init__(
        self,
        model_id: str = None,
        dtype_name: str = "bfloat16",
        enable_attention_slicing: bool = True,
        enable_vae_slicing: bool = True,
    ):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.dtype_name = dtype_name
        self._pipe: Optional[DiffusionPipeline] = None
        self._enable_attention_slicing = enable_attention_slicing
        self._enable_vae_slicing = enable_vae_slicing

    # ── Lazy loading ─────────────────────────────────────────────────────────

    def _ensure_pipe(self) -> Optional[DiffusionPipeline]:
        if self._pipe is None:
            self._pipe = _load_pipeline(self.model_id, self.dtype_name)
            if self._pipe is not None:
                if self._enable_attention_slicing:
                    self._pipe.enable_attention_slicing()
                if self._enable_vae_slicing:
                    self._pipe.enable_vae_slicing()
        return self._pipe

    def unload(self) -> None:
        """Release GPU memory held by the pipeline."""
        if self._pipe is not None:
            import torch
            del self._pipe
            self._pipe = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("[ImageGen] Pipeline unloaded")

    # ── Generation methods ───────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        size: tuple[int, int] = None,
        steps: int = 25,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> Optional[Image.Image]:
        """
        Text-to-image generation.

        Args:
            prompt: English text description
            negative_prompt: Things to avoid
            size: (width, height) — defaults to 1024x1024
            steps: Number of inference steps
            guidance_scale: CFG scale
            seed: Fixed random seed (None = random)

        Returns:
            PIL Image or None on failure.
        """
        pipe = self._ensure_pipe()
        if pipe is None:
            return None

        width, height = size or self.DEFAULT_SIZE

        gen_kwargs: dict = {"num_inference_steps": steps, "guidance_scale": guidance_scale}
        if seed is not None:
            import torch
            gen_kwargs["generator"] = torch.Generator(device=_get_device()).manual_seed(seed)

        try:
            result = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                width=width,
                height=height,
                **gen_kwargs,
            )
            return result.images[0] if hasattr(result, "images") else result[0]
        except Exception as e:
            logger.warning("[ImageGen] generate failed: %s", e)
            return None

    def generate_with_image(
        self,
        prompt: str,
        reference_image: Image.Image | str,
        strength: float = 0.6,
        steps: int = 25,
        guidance_scale: float = 7.5,
    ) -> Optional[Image.Image]:
        """
        Image-to-image generation (style/content consistency).

        Args:
            prompt: Target description
            reference_image: PIL Image or base64 string
            strength: How much to transform (0=unchanged, 1=full change)
            steps, guidance_scale: Same as generate()

        Returns:
            PIL Image or None on failure.
        """
        pipe = self._ensure_pipe()
        if pipe is None:
            return None

        # Accept base64 input
        if isinstance(reference_image, str):
            reference_image = self._base64_to_pil(reference_image)
        if reference_image is None:
            return None

        try:
            from diffusers import StableDiffusionImg2ImgPipeline
            if not hasattr(pipe, "refiner") and not hasattr(pipe, "image_encoder"):
                # Use the same pipe in img2img mode if it supports it
                img_pipe = pipe
            else:
                img_pipe = pipe

            result = img_pipe(
                prompt=prompt,
                image=reference_image,
                strength=strength,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
            )
            return result.images[0] if hasattr(result, "images") else result[0]
        except Exception as e:
            logger.warning("[ImageGen] generate_with_image failed: %s", e)
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

        Args:
            prompt: What to fill in the masked area
            reference_image: PIL Image or base64 string (the base image)
            mask_image: PIL Image (white=inpaint, black=keep)
            steps, guidance_scale: Same as generate()

        Returns:
            PIL Image or None on failure.
        """
        pipe = self._ensure_pipe()
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
            logger.warning("[ImageGen] generate_inpaint failed: %s", e)
            return None

    # ── Serialization ────────────────────────────────────────────────────────

    @staticmethod
    def pil_to_base64(image: Image.Image, format: str = "PNG") -> Optional[str]:
        """Convert PIL Image to base64 data URL."""
        if image is None:
            return None
        try:
            buf = io.BytesIO()
            image.save(buf, format=format)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/{format.lower()};base64,{b64}"
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

_img_gen: Optional[LocalImageGenerator] = None


def get_image_generator() -> LocalImageGenerator:
    """Return the shared LocalImageGenerator singleton."""
    global _img_gen
    if _img_gen is None:
        _img_gen = LocalImageGenerator()
    return _img_gen


def configure_image_generator(model_id: str, dtype_name: str) -> None:
    """Reconfigure the shared generator (e.g. from Settings)."""
    global _img_gen
    _img_gen = LocalImageGenerator(model_id=model_id, dtype_name=dtype_name)
    logger.info("[ImageGen] Configured: model_id=%s dtype=%s", model_id, dtype_name)
