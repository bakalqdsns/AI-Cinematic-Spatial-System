"""
DashScope provider — wraps the official dashscope SDK.

Supports LLM (Generation), VLM (MultiModalConversation), Image (ImageSynthesis),
and Video (VideoSynthesis). API keys are passed per-call from the provider config,
falling back to environment variables when not provided.

Existing dashscope_client.py / video_adapter.py continue to work for legacy call
sites. This class is the unified entry point used by CloudRouter.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from app.providers.base import BaseProvider, normalize_image_to_b64, make_data_uri
from app.config import CACHE_DIR

logger = logging.getLogger(__name__)


class DashScopeProvider(BaseProvider):
    """
    DashScope SDK-backed provider.

    Config block:
        {
            "type": "dashscope",
            "api_key": "sk-xxx",            # optional; falls back to env
            "base_url": "...",              # optional; SDK default endpoint used when absent
        }

    Note: the dashscope SDK does not currently support a custom base_url; the
    field is accepted but ignored. Use this provider for the official Alibaba
    Cloud endpoint only.
    """

    type = "dashscope"

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        # Fall back to env if no key in config
        if not self.api_key:
            self.api_key = os.environ.get("DASHSCOPE_API_KEY", "")

    # ── LLM ──────────────────────────────────────────────────────────────────
    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        try:
            from dashscope import Generation
        except ImportError as e:
            raise RuntimeError(
                "dashscope SDK not installed. Run: pip install dashscope"
            ) from e

        def _call():
            resp = Generation.call(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                result_format="message",
                api_key=self.api_key,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"DashScope Generation API error {resp.status_code}: "
                    f"{getattr(resp, 'message', resp)}"
                )
            output = resp.output
            if hasattr(output, "choices") and output.choices:
                return output.choices[0].message.content or ""
            if hasattr(output, "text") and output.text:
                return output.text
            return str(output)

        return await asyncio.to_thread(_call)

    # ── VLM ──────────────────────────────────────────────────────────────────
    async def vlm_analyze(
        self,
        image: str,
        prompt: str,
        model: str,
        **kwargs,
    ) -> str:
        try:
            from dashscope import MultiModalConversation
        except ImportError as e:
            raise RuntimeError("dashscope SDK not installed") from e

        b64 = normalize_image_to_b64(image)
        data_uri = make_data_uri(b64, mime="image/jpeg")

        def _call():
            resp = MultiModalConversation.call(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": data_uri},
                            {"text": prompt},
                        ],
                    }
                ],
                api_key=self.api_key,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"DashScope VLM API error {resp.status_code}: "
                    f"{getattr(resp, 'message', resp)}"
                )
            return resp.output.choices[0].message.content or ""

        return await asyncio.to_thread(_call)

    # ── Image ────────────────────────────────────────────────────────────────
    async def generate_image(
        self,
        prompt: str,
        model: str,
        size: str = "1024*1024",
        n: int = 1,
        **kwargs,
    ) -> list[str]:
        try:
            from dashscope import ImageSynthesis
        except ImportError as e:
            raise RuntimeError("dashscope SDK not installed") from e

        def _call():
            resp = ImageSynthesis.call(
                model=model,
                prompt=prompt,
                size=size,
                n=n,
                api_key=self.api_key,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"DashScope ImageSynthesis API error {resp.status_code}: "
                    f"{getattr(resp, 'message', resp)}"
                )
            images = resp.output.get("results") or resp.output.get("images") or []
            urls = []
            for img in images:
                url = img.get("url") if isinstance(img, dict) else None
                if url:
                    urls.append(url)
                elif hasattr(img, "url"):
                    urls.append(img.url)
                else:
                    urls.append(str(img))
            return urls

        return await asyncio.to_thread(_call)

    # ── Video ────────────────────────────────────────────────────────────────
    async def generate_video(
        self,
        prompt: str,
        model: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
        **kwargs,
    ) -> Optional[str]:
        try:
            from dashscope import VideoSynthesis
        except ImportError as e:
            raise RuntimeError("dashscope SDK not installed") from e

        def b64_to_uri(b64: str) -> str:
            if b64.startswith("data:"):
                return b64
            return f"data:image/png;base64,{b64}"

        # Submit
        call_kwargs: dict = {
            "model": model,
            "prompt": prompt,
            "api_key": self.api_key,
        }
        if start_image_b64:
            call_kwargs["first_frame_url"] = b64_to_uri(start_image_b64)
        if end_image_b64:
            call_kwargs["last_frame_url"] = b64_to_uri(end_image_b64)

        try:
            task_resp = await asyncio.to_thread(VideoSynthesis.call, **call_kwargs)
        except Exception as e:
            logger.warning("[DashScope:%s] video submit error: %s", self.name, e)
            return None

        if getattr(task_resp, "status_code", 500) != 200:
            logger.warning("[DashScope:%s] video submit failed: %s", self.name, getattr(task_resp, "message", task_resp))
            return None

        task_id = getattr(task_resp.output, "task_id", None)
        if not task_id:
            logger.warning("[DashScope:%s] no task_id in response", self.name)
            return None
        logger.info("[DashScope:%s] video task created: %s", self.name, task_id)

        # Poll
        poll_intervals = [5, 10, 15, 20, 30]
        elapsed = 0
        poll_idx = 0
        while elapsed < 300:
            interval = poll_intervals[min(poll_idx, len(poll_intervals) - 1)]
            await asyncio.sleep(interval)
            elapsed += interval
            poll_idx += 1
            try:
                status_resp = await asyncio.to_thread(
                    VideoSynthesis.fetch, task_id=task_id, api_key=self.api_key,
                )
                task_status = status_resp.output.task_status
                if task_status == "succeed":
                    video_url = status_resp.output.video.video_url
                    return await self._download_video(video_url)
                if task_status in ("failed", "error"):
                    logger.warning("[DashScope:%s] video failed: %s", self.name, status_resp.output)
                    return None
            except Exception as e:
                logger.warning("[DashScope:%s] poll error: %s", self.name, e)
                continue

        logger.warning("[DashScope:%s] video timed out after %ds", self.name, elapsed)
        return None

    async def _download_video(self, url: str) -> Optional[str]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                cache_dir = CACHE_DIR / "videos"
                cache_dir.mkdir(parents=True, exist_ok=True)
                video_path = cache_dir / f"{uuid.uuid4().hex[:8]}.mp4"
                with open(video_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
            return str(video_path)
        except Exception as e:
            logger.warning("[DashScope:%s] download failed: %s", self.name, e)
            return None
