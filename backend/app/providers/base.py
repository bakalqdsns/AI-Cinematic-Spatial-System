"""
Base provider interface for AICSS cloud model adapters.

This module defines the unified BaseProvider contract that all cloud
provider implementations must satisfy. The goal is to allow third-party
APIs (OpenAI-compatible, DashScope, custom REST) to be added to the
system purely through configuration, without backend code changes.

Each provider implements four capability methods:
  - chat()             → text generation
  - vlm_analyze()      → image understanding
  - generate_image()   → text-to-image
  - generate_video()   → text-to-video (returns local file path)

Implementations are responsible for ALL provider-specific knowledge:
authentication, request format, response parsing, async task polling,
video file download, etc. The router layer only sees these four methods.

Adding a new provider = subclass BaseProvider + register_provider(name, cls).
"""
from __future__ import annotations

import base64
import io
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_image_to_b64(image, mime: str = "image/jpeg") -> str:
    """
    Normalize a PIL Image / base64 string / data-URI to a raw base64 string
    (no prefix). Used internally by providers that don't need a data URI.

    Args:
        image: PIL Image, raw base64 string, or data URI like "data:image/...;base64,xxx"
        mime: JPEG/PNG etc. for PIL encoding (default JPEG, smaller).

    Returns:
        Raw base64 string WITHOUT the "data:image/...;base64," prefix.
    """
    from PIL import Image
    if isinstance(image, Image.Image):
        buf = io.BytesIO()
        image.save(buf, format="JPEG" if mime == "image/jpeg" else "PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    s = image.strip()
    if s.startswith("data:"):
        idx = s.find("base64,")
        if idx >= 0:
            return s[idx + 7:]
    return s


def make_data_uri(b64: str, mime: str = "image/jpeg") -> str:
    """Wrap a raw base64 string as a data URI."""
    if b64.startswith("data:"):
        return b64
    return f"data:{mime};base64,{b64}"


class BaseProvider(ABC):
    """
    Unified provider interface — all cloud providers implement this.

    Every method takes api_key and base_url explicitly so the router can
    forward user-configured credentials without the provider needing to
    read global state.

    Required constructor signature:
        Provider(name: str, config: dict)

    Where config is the user-defined provider block from settings, e.g.:
        {
            "type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-xxx",
            "extra_headers": {...},   # optional
            "extra_json": {...},      # optional
        }
    """

    name: str = "base"
    type: str = "base"

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config or {}
        self.api_key = self.config.get("api_key", "")
        self.base_url = (self.config.get("base_url") or "").rstrip("/")

    # ── LLM: Chat ────────────────────────────────────────────────────────────
    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        """
        Synchronous-style chat completion (returns plain text).

        Implementations may override this. The default raises NotImplementedError.
        """
        raise NotImplementedError(
            f"Provider {self.name!r} does not support chat"
        )

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        """Raw completion. Default implementation routes through chat()."""
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    # ── VLM: Image analysis ──────────────────────────────────────────────────
    async def vlm_analyze(
        self,
        image: str,
        prompt: str,
        model: str,
        **kwargs,
    ) -> str:
        """Vision-language analysis. Returns plain text response."""
        raise NotImplementedError(
            f"Provider {self.name!r} does not support vlm_analyze"
        )

    # ── Image: Text-to-image ─────────────────────────────────────────────────
    async def generate_image(
        self,
        prompt: str,
        model: str,
        size: str = "1024*1024",
        n: int = 1,
        **kwargs,
    ) -> list[str]:
        """Returns a list of image URLs (or local file paths / data URIs)."""
        raise NotImplementedError(
            f"Provider {self.name!r} does not support generate_image"
        )

    # ── Video: Text-to-video ─────────────────────────────────────────────────
    async def generate_video(
        self,
        prompt: str,
        model: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
        **kwargs,
    ) -> Optional[str]:
        """Returns a local file path to the generated video, or None on failure."""
        raise NotImplementedError(
            f"Provider {self.name!r} does not support generate_video"
        )

    # ── Health check ─────────────────────────────────────────────────────────
    async def is_alive(self) -> bool:
        """Optional liveness probe. Default checks /models endpoint if base_url set."""
        if not self.base_url:
            return True
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False

    # ── Capability flags (override in subclasses) ────────────────────────────
    @property
    def supports_chat(self) -> bool:
        return type(self).chat is not BaseProvider.chat

    @property
    def supports_vlm(self) -> bool:
        return type(self).vlm_analyze is not BaseProvider.vlm_analyze

    @property
    def supports_image(self) -> bool:
        return type(self).generate_image is not BaseProvider.generate_image

    @property
    def supports_video(self) -> bool:
        return type(self).generate_video is not BaseProvider.generate_video
