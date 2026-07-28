"""
DashScope API Client — unified LLM + VLM + Image generation.

This module provides cloud-side model inference via DashScope, as an alternative
to local models. In "cloud" mode (the default), AICSS uses:

  - LLM:        qwen3.7-plus (via Generation)
  - VLM:        qwen3-vl-flash-2026-01-22 (via MultiModalConversation)
  - Image Gen:  wan2.7-image-pro (via ImageSynthesis)

Cloud mode avoids launching llama-server and loading local checkpoints, saving
~16-22 GB of GPU/CPU memory on machines that don't need local inference.

API key routing
---------------
Each component (LLM / VLM / image) has its own API key field on the settings
panel. At call time, we resolve the key for the component being called and
pass it explicitly via the `api_key=` kwarg to the DashScope SDK so the right
credential is used regardless of any process-wide ``dashscope.api_key`` state.
Fallback order:
  1. The per-component setting (e.g. ``dashscope_llm_api_key``).
  2. ``DASHSCOPE_API_KEY`` env var (legacy / single-key deployments).
  3. ``dashscope.api_key`` (set elsewhere at startup).
  4. Empty string — caller will surface a clear "missing key" error.

Usage:
    client = DashScopeClient()
    text = client.chat([{"role": "user", "content": "Hello"}])
    result = client.vlm_analyze(image_base64, "Describe this scene")
    image_url = client.generate_image("a cat sitting on a desk", size="1024*1024")
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

from PIL import Image
import io

logger = logging.getLogger(__name__)

# Default model IDs (can be overridden at construction or via config)
DEFAULT_LLM_MODEL = "qwen3.7-plus"
DEFAULT_VLM_MODEL = "qwen3-vl-flash-2026-01-22"
DEFAULT_IMAGE_MODEL = "wan2.7-image-pro"


def _resolve_llm_key() -> str:
    from app.config import settings
    if settings.dashscope_llm_api_key:
        return settings.dashscope_llm_api_key
    return os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("DASHSCOPE_LLM_API_KEY", "")


def _resolve_vlm_key() -> str:
    from app.config import settings
    if settings.dashscope_vlm_api_key:
        return settings.dashscope_vlm_api_key
    return os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("DASHSCOPE_VLM_API_KEY", "")


def _resolve_image_key() -> str:
    from app.config import settings
    if settings.dashscope_image_api_key:
        return settings.dashscope_image_api_key
    return os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("DASHSCOPE_IMAGE_API_KEY", "")


class DashScopeClient:
    """
    Unified client for DashScope APIs.

    Supports:
      - Text generation (Generation API)
      - Vision-language analysis (MultiModalConversation API)
      - Text-to-image synthesis (ImageSynthesis API)
    """

    def __init__(
        self,
        llm_model: str = DEFAULT_LLM_MODEL,
        vlm_model: str = DEFAULT_VLM_MODEL,
        image_model: str = DEFAULT_IMAGE_MODEL,
    ):
        self.llm_model = llm_model
        self.vlm_model = vlm_model
        self.image_model = image_model
        logger.info(
            "[DashScopeClient] Initialized — LLM=%s VLM=%s Image=%s",
            self.llm_model, self.vlm_model, self.image_model,
        )

    # ── LLM: Text Generation ───────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        Send a chat conversation and return the assistant's text response.

        Args:
            messages: List of {"role": "user"|"system"|"assistant", "content": str}
            temperature: Sampling temperature (0 = deterministic)
            max_tokens: Maximum new tokens to generate

        Returns:
            The assistant's message content as a plain string.

        Raises:
            RuntimeError: If the API call fails or returns an error status.
        """
        try:
            from dashscope import Generation
        except ImportError as e:
            raise RuntimeError(
                "dashscope SDK not installed. Run: pip install dashscope"
            ) from e

        try:
            response = Generation.call(
                model=self.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                result_format="message",
                api_key=_resolve_llm_key(),
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"DashScope Generation API error {response.status_code}: "
                    f"{getattr(response, 'message', response)}"
                )
            choice = response.output.choices[0]
            return choice.message.content or ""
        except Exception as e:
            logger.error("[DashScopeClient.chat] Error: %s", e)
            raise RuntimeError(f"DashScope chat failed: {e}") from e

    # ── VLM: Vision-Language Analysis ─────────────────────────────────────────

    def vlm_analyze(self, image: str | Image.Image, prompt: str) -> str:
        """
        Analyze an image using a vision-language model.

        Args:
            image: Image as a base64 string (with or without data-URI prefix) or
                   a PIL Image object.
            prompt: Text prompt or question to ask about the image.

        Returns:
            The model's text response.
        """
        try:
            from dashscope import MultiModalConversation
        except ImportError as e:
            raise RuntimeError(
                "dashscope SDK not installed. Run: pip install dashscope"
            ) from e

        # Normalize image to base64 data-URI
        b64 = self._normalize_image(image)

        try:
            response = MultiModalConversation.call(
                model=self.vlm_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": b64},
                            {"text": prompt},
                        ],
                    }
                ],
                api_key=_resolve_vlm_key(),
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"DashScope VLM API error {response.status_code}: "
                    f"{getattr(response, 'message', response)}"
                )
            return response.output.choices[0].message.content or ""
        except Exception as e:
            logger.error("[DashScopeClient.vlm_analyze] Error: %s", e)
            raise RuntimeError(f"DashScope VLM analysis failed: {e}") from e

    # ── Image Generation ───────────────────────────────────────────────────────

    def generate_image(
        self,
        prompt: str,
        size: str = "1024*1024",
        n: int = 1,
    ) -> list[str]:
        """
        Generate images from a text prompt using wan2.7-image-pro.

        Args:
            prompt: Text description of the desired image.
            size:   Output resolution in W*H format, e.g. "1024*1024",
                    "720*1280", "1280*720".
            n:      Number of images to generate (max 4 per request).

        Returns:
            List of image URLs ( DashScope stores results temporarily).
        """
        try:
            from dashscope import ImageSynthesis
        except ImportError as e:
            raise RuntimeError(
                "dashscope SDK not installed. Run: pip install dashscope"
            ) from e

        try:
            response = ImageSynthesis.call(
                model=self.image_model,
                prompt=prompt,
                size=size,
                n=n,
                api_key=_resolve_image_key(),
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"DashScope ImageSynthesis API error {response.status_code}: "
                    f"{getattr(response, 'message', response)}"
                )
            images = response.output.images
            return [img.url for img in images] if images else []
        except Exception as e:
            logger.error("[DashScopeClient.generate_image] Error: %s", e)
            raise RuntimeError(f"DashScope image generation failed: {e}") from e

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_image(image: str | Image.Image) -> str:
        """
        Convert various image representations to a base64 data URI string
        accepted by MultiModalConversation.

        Args:
            image: PIL Image or base64 string (with or without data-URI prefix).

        Returns:
            Data URI string, e.g. "data:image/jpeg;base64,<b64>".
        """
        if isinstance(image, Image.Image):
            buf = io.BytesIO()
            image.save(buf, format="JPEG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"

        # Already a string — check for data-URI prefix
        image = image.strip()
        if image.startswith("data:"):
            return image
        # Assume raw base64 (add JPEG prefix)
        return f"data:image/jpeg;base64,{image}"


# ── Module-level singleton ────────────────────────────────────────────────────

_dashscope_client: Optional[DashScopeClient] = None


def get_dashscope_client() -> DashScopeClient:
    """Return the shared DashScopeClient singleton."""
    global _dashscope_client
    if _dashscope_client is None:
        _dashscope_client = DashScopeClient()
    return _dashscope_client


def configure_dashscope_client(
    llm_model: str | None = None,
    vlm_model: str | None = None,
    image_model: str | None = None,
) -> DashScopeClient:
    """Create (or recreate) the shared DashScopeClient with the given model IDs.

    Only values that are not None will override the existing client. This allows
    partial updates without having to specify all model IDs.
    """
    global _dashscope_client
    if _dashscope_client is None:
        _dashscope_client = DashScopeClient()
    if llm_model is not None:
        _dashscope_client.llm_model = llm_model
    if vlm_model is not None:
        _dashscope_client.vlm_model = vlm_model
    if image_model is not None:
        _dashscope_client.image_model = image_model
    logger.info(
        "[DashScopeClient] Reconfigured — LLM=%s VLM=%s Image=%s",
        _dashscope_client.llm_model, _dashscope_client.vlm_model, _dashscope_client.image_model,
    )
    return _dashscope_client
