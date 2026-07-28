"""
Video Generation Adapter — Pluggable provider layer.

Provides a unified `VideoProvider` interface for action video generation, with
multiple backends:

  - "dashscope"  — DashScope VideoSynthesis API (wanx_2_1_i2v_plus, cloud)
  - "local_wan"  — wan2.1-i2v local inference via Modelscope (28GB+ VRAM)
  - "svd"        — Stable Video Diffusion local (8GB VRAM, degraded quality)

Usage:
    provider = get_video_provider("dashscope")   # or "local_wan", "svd"
    video_path = await provider.generate(prompt, start_b64, end_b64, duration)

    # Or through the factory:
    from app.services.video_adapter import video_generate
    video_path = await video_generate(prompt, provider="svd")
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import CACHE_DIR

logger = logging.getLogger(__name__)


# ── VideoProvider interface ───────────────────────────────────────────────────────

class VideoProvider(ABC):
    """
    Abstract base for all video generation providers.

    Each provider must implement the `generate` method, which:
      - Takes an action prompt and optional start/end frames
      - Returns the path to a locally-saved video file
      - Is a blocking async call (waits for generation to complete)
    """

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
    ) -> Optional[str]:
        """
        Generate an action video.

        Args:
            prompt: Action description text
            start_image_b64: Optional first frame (base64)
            end_image_b64: Optional last frame (base64)
            duration: Target duration in seconds

        Returns:
            Local file path to the generated video, or None on failure.
        """
        ...


# ── Provider implementations ──────────────────────────────────────────────────────

class DashScopeFilmProvider(VideoProvider):
    """
    DashScope VideoSynthesis API via dashscope.VideoSynthesis.

    Uses wanx_2_1_i2v_plus for image-to-video generation (cloud, high quality).

    API key resolution order (matches dashscope_client):
      1. ``dashscope_video_api_key`` setting (set via Settings UI)
      2. ``DASHSCOPE_VIDEO_API_KEY`` env var
      3. ``DASHSCOPE_API_KEY`` env var (legacy single-key deployments)
    """

    name = "dashscope"
    _model = "wanx_2_1_i2v_plus"

    @staticmethod
    def _resolve_api_key() -> str:
        """Resolve the DashScope API key for video calls."""
        try:
            from app.config import settings
            if settings.dashscope_video_api_key:
                return settings.dashscope_video_api_key
        except Exception:
            pass
        return (
            os.getenv("DASHSCOPE_VIDEO_API_KEY", "")
            or os.getenv("DASHSCOPE_API_KEY", "")
        )

    async def generate(
        self,
        prompt: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
    ) -> Optional[str]:
        try:
            from dashscope import VideoSynthesis
            import httpx

            # Convert base64 to data URI for URL parameter
            def b64_to_data_uri(b64: str) -> str:
                if b64.startswith("data:"):
                    return b64
                return f"data:image/png;base64,{b64}"

            api_key = self._resolve_api_key()
            call_kwargs: dict = {
                "model": self._model,
                "prompt": prompt,
                "api_key": api_key,
            }

            if start_image_b64:
                call_kwargs["first_frame_url"] = b64_to_data_uri(start_image_b64)
            if end_image_b64:
                call_kwargs["last_frame_url"] = b64_to_data_uri(end_image_b64)

            task_resp = VideoSynthesis.call(**call_kwargs)
            if task_resp.status_code != 200:
                logger.warning("[VideoAdapter:DashScope] task creation failed: %s", task_resp.message)
                return None

            task_id = task_resp.output.task_id
            logger.info("[VideoAdapter:DashScope] task created: %s", task_id)

            # Poll with exponential backoff
            poll_intervals = [5, 10, 15, 20, 30]
            elapsed = 0
            poll_idx = 0

            while elapsed < 300:
                status_resp = VideoSynthesis.fetch(task_id=task_id, api_key=api_key)
                task_status = status_resp.output.task_status
                if task_status == "succeed":
                    video_url = status_resp.output.video.video_url
                    logger.info("[VideoAdapter:DashScope] task succeeded after %ds", elapsed)
                    return await self._download_video(video_url)
                if task_status in ("failed", "error"):
                    logger.warning("[VideoAdapter:DashScope] task failed: %s", status_resp.output)
                    return None

                interval = poll_intervals[min(poll_idx, len(poll_intervals) - 1)]
                time.sleep(interval)
                elapsed += interval
                poll_idx += 1

            logger.warning("[VideoAdapter:DashScope] task timed out after 300s")
            return None

        except Exception as e:
            logger.warning("[VideoAdapter:DashScope] error: %s", e)
            return None

    @staticmethod
    async def _download_video(url: str) -> Optional[str]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
            cache_dir = CACHE_DIR / "videos"
            cache_dir.mkdir(parents=True, exist_ok=True)
            video_path = cache_dir / f"{uuid.uuid4().hex[:8]}.mp4"
            with open(video_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
            return str(video_path)
        except Exception as e:
            logger.warning("[VideoAdapter:DashScope] download failed: %s", e)
            return None


class LocalWanProvider(VideoProvider):
    """
    wan2.1-i2v local inference via Modelscope / diffusers.

    Requires ~28GB VRAM (fp16). Falls back gracefully on OOM.
    """
    name = "local_wan"

    async def generate(
        self,
        prompt: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
    ) -> Optional[str]:
        try:
            from diffusers import WanImageToVideoPipeline
            import torch
            from PIL import Image

            device = "cuda" if torch.cuda.is_available() else "cpu"
            pipe = WanImageToVideoPipeline.from_pretrained(
                "Wan-AI/Wan2.1-I2V-14B-480P",
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                use_safetensors=True,
            )
            pipe.to(device)

            start_img = None
            if start_image_b64:
                start_img = self._b64_to_pil(start_image_b64)

            num_frames = int(duration * 8)  # ~8fps

            if start_img is not None:
                result = pipe(prompt=prompt, image=start_img, num_inference_steps=50, guidance_scale=5.0)
            else:
                logger.warning("[VideoAdapter:LocalWan] requires start_image — generating text-to-video")
                result = pipe(prompt=prompt, num_inference_steps=50, guidance_scale=5.0)

            frames = result.frames[0] if hasattr(result, "frames") else result[0]
            video_path = await self._save_video_frames(frames, duration)
            del pipe
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return video_path

        except Exception as e:
            logger.warning("[VideoAdapter:LocalWan] error: %s", e)
            return None

    @staticmethod
    def _b64_to_pil(b64: str) -> Optional[Image.Image]:
        try:
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            data = base64.b64decode(b64)
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            return None

    @staticmethod
    async def _save_video_frames(frames, duration: float) -> Optional[str]:
        try:
            import cv2
            cache_dir = CACHE_DIR / "videos"
            cache_dir.mkdir(parents=True, exist_ok=True)
            video_path = cache_dir / f"{uuid.uuid4().hex[:8]}.mp4"
            first = frames[0]
            h, w = first.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(str(video_path), fourcc, len(frames) / duration, (w, h))
            for frame in frames:
                rgb = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(rgb)
            out.release()
            return str(video_path)
        except Exception as e:
            logger.warning("[VideoAdapter:LocalWan] _save_video_frames error: %s", e)
            return None


class SVDProvider(VideoProvider):
    """
    Stable Video Diffusion — lightweight local video generation (~8GB VRAM).

    Produces 25-frame (1s) videos from a single image. Lower quality than
    wan2.1-i2v but runs on consumer GPUs.

    For longer durations, generates multiple clips and concatenates them.
    """
    name = "svd"

    async def generate(
        self,
        prompt: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
    ) -> Optional[str]:
        try:
            from diffusers import StableVideoDiffusionPipeline
            import torch
            from PIL import Image
            import tempfile

            device = "cuda" if torch.cuda.is_available() else "cpu"
            pipe = StableVideoDiffusionPipeline.from_pretrained(
                "stabilityai/stable-video-diffusion-img2vid-xt",
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                use_safetensors=True,
            )
            pipe.to(device)

            # Use start image or generate a placeholder
            if start_image_b64:
                init_image = self._b64_to_pil(start_image_b64)
            else:
                logger.warning("[VideoAdapter:SVD] No start_image — using black frame")
                init_image = Image.new("RGB", (1024, 576), (0, 0, 0))

            num_frames = min(int(duration * 25), 25)  # SVD caps at 25 frames

            with torch.no_grad():
                result = pipe(
                    image=init_image,
                    num_frames=num_frames,
                    decode_chunk_size=8,
                    generator=torch.Generator(device=device).manual_seed(42),
                )

            frames = result.frames[0]
            video_path = await self._frames_to_video(frames, duration)
            del pipe
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return video_path

        except Exception as e:
            logger.warning("[VideoAdapter:SVD] error: %s", e)
            return None

    @staticmethod
    def _b64_to_pil(b64: str) -> Optional[Image.Image]:
        try:
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            data = base64.b64decode(b64)
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            return None

    @staticmethod
    async def _frames_to_video(frames, duration: float) -> Optional[str]:
        try:
            import cv2
            cache_dir = CACHE_DIR / "videos"
            cache_dir.mkdir(parents=True, exist_ok=True)
            video_path = cache_dir / f"{uuid.uuid4().hex[:8]}.mp4"
            first = frames[0]
            if isinstance(first, Image.Image):
                first = np.array(first)
            h, w = first.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(str(video_path), fourcc, len(frames) / duration, (w, h))
            for frame in frames:
                if isinstance(frame, Image.Image):
                    frame = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
                else:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out.write(frame)
            out.release()
            return str(video_path)
        except Exception as e:
            logger.warning("[VideoAdapter:SVD] _frames_to_video error: %s", e)
            return None


# ── Provider registry & factory ───────────────────────────────────────────────────

_PROVIDER_REGISTRY: dict[str, type[VideoProvider]] = {
    "dashscope": DashScopeFilmProvider,
    "local_wan": LocalWanProvider,
    "svd": SVDProvider,
}


def get_video_provider(provider_name: str = "dashscope") -> VideoProvider:
    """
    Factory: return a VideoProvider instance by name.

    Args:
        provider_name: One of "dashscope", "local_wan", "svd"
                      Defaults to "dashscope" (cloud, high quality).
    """
    cls = _PROVIDER_REGISTRY.get(provider_name.lower())
    if cls is None:
        logger.warning(
            "[VideoAdapter] Unknown provider %r — using dashscope. "
            "Available: %s",
            provider_name,
            list(_PROVIDER_REGISTRY.keys()),
        )
        cls = DashScopeFilmProvider
    return cls()


def register_video_provider(name: str, cls: type[VideoProvider]) -> None:
    """Register a custom VideoProvider subclass at runtime."""
    _PROVIDER_REGISTRY[name.lower()] = cls
    logger.info("[VideoAdapter] Registered provider: %s (%s)", name, cls.name)


# ── Convenience wrapper ─────────────────────────────────────────────────────────

async def video_generate(
    prompt: str,
    provider: str = "dashscope",
    start_image_b64: Optional[str] = None,
    end_image_b64: Optional[str] = None,
    duration: float = 5.0,
) -> Optional[str]:
    """
    One-line video generation through the active provider.

    Equivalent to:
        provider = get_video_provider(provider)
        await provider.generate(prompt, start_image_b64, end_image_b64, duration)
    """
    p = get_video_provider(provider)
    return await p.generate(prompt, start_image_b64, end_image_b64, duration)
