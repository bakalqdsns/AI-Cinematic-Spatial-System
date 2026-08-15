"""
Generic OpenAI-compatible provider.

This provider talks to any service that exposes an OpenAI-compatible API:
  - /v1/chat/completions  (LLM chat, including vision via image_url)
  - /v1/images/generations (text-to-image)
  - /v1/videos/generations + /v1/videos/generations/{task_id}  (text-to-video, async)

Supported services include ToAPIs, SiliconFlow, Groq, Fireworks, OpenRouter, etc.
Adding support for a new OpenAI-compatible service requires no backend code —
just a new entry in the provider registry.

Reference: https://docs.toapis.com/docs/cn/quickstart
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

import httpx

from app.providers.base import BaseProvider, normalize_image_to_b64
from app.config import CACHE_DIR

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    """
    Generic OpenAI-compatible provider supporting all four capabilities.

    Config block (from settings):
        {
            "type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-xxx",
            "extra_headers": {"X-App-Id": "..."},   # optional
            "extra_json":   {"response_format": ...} # optional, merged into chat/image payloads
        }
    """

    type = "openai_compatible"
    DEFAULT_TIMEOUT = 120.0

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        # User-defined extra headers (e.g. ToAPIs webhook signing, custom auth)
        extra = self.config.get("extra_headers") or {}
        if isinstance(extra, dict):
            h.update({str(k): str(v) for k, v in extra.items()})
        return h

    def _client(self, timeout: Optional[float] = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout or self.DEFAULT_TIMEOUT,
            http2=False,
            trust_env=False,
            headers=self._headers(),
        )

    def _auth_headers_no_auth(self) -> dict:
        """For /models health check that may not require auth."""
        h = self._headers()
        # Keep headers; some providers accept Bearer on /models, others don't
        return h

    # ── LLM ──────────────────────────────────────────────────────────────────
    async def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> str:
        payload: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop
        extra_json = self.config.get("extra_json") or {}
        if isinstance(extra_json, dict):
            payload.update(extra_json)

        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
            if resp.status_code >= 400:
                logger.error(
                    "[OpenAICompat:%s] chat HTTP %d: %s",
                    self.name, resp.status_code, resp.text[:500],
                )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            logger.error("[OpenAICompat:%s] chat failed: %s", self.name, e)
            raise

    # ── VLM ──────────────────────────────────────────────────────────────────
    async def vlm_analyze(
        self,
        image: str,
        prompt: str,
        model: str,
        **kwargs,
    ) -> str:
        b64 = normalize_image_to_b64(image)
        data_uri = f"data:image/jpeg;base64,{b64}"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        extra_json = self.config.get("extra_json") or {}
        if isinstance(extra_json, dict):
            payload.update(extra_json)

        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            logger.error("[OpenAICompat:%s] vlm_analyze failed: %s", self.name, e)
            raise

    # ── Image ────────────────────────────────────────────────────────────────
    async def generate_image(
        self,
        prompt: str,
        model: str,
        size: str = "1024*1024",
        n: int = 1,
        **kwargs,
    ) -> list[str]:
        # Convert "1024*1024" → "1024x1024" for OpenAI-style
        size_normalized = size.replace("*", "x")
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size_normalized,
        }
        extra_json = self.config.get("extra_json") or {}
        if isinstance(extra_json, dict):
            payload.update(extra_json)

        async with self._client() as client:
            resp = await client.post(
                f"{self.base_url}/images/generations",
                json=payload,
            )
            if resp.status_code >= 400:
                logger.error(
                    "[OpenAICompat:%s] image HTTP %d: %s",
                    self.name, resp.status_code, resp.text[:500],
                )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data") or []
            # Return list of URLs (or b64_json if no URL)
            return [
                item.get("url") or f"data:image/png;base64,{item['b64_json']}"
                for item in items
            ]

    # ── Video (async task with polling) ──────────────────────────────────────
    async def generate_video(
        self,
        prompt: str,
        model: str,
        start_image_b64: Optional[str] = None,
        end_image_b64: Optional[str] = None,
        duration: float = 5.0,
        **kwargs,
    ) -> Optional[str]:
        """
        Submit an async video generation task, poll until done, download the
        result, and return the local file path. Mirrors the ToAPIs reference
        flow (https://docs.toapis.com/docs/cn/quickstart).

        Polling intervals: 5, 10, 15, 20, 30s, max 300s total.
        """
        # Step 1: Submit task
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "duration": int(duration),
        }
        if start_image_b64:
            payload["image"] = f"data:image/jpeg;base64,{normalize_image_to_b64(start_image_b64)}"
        elif end_image_b64:
            payload["image"] = f"data:image/jpeg;base64,{normalize_image_to_b64(end_image_b64)}"

        try:
            async with self._client(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/videos/generations",
                    json=payload,
                )
            if resp.status_code >= 400:
                logger.error(
                    "[OpenAICompat:%s] video submit HTTP %d: %s",
                    self.name, resp.status_code, resp.text[:500],
                )
            resp.raise_for_status()
            submit_data = resp.json()
            task_id = (
                submit_data.get("task_id")
                or submit_data.get("id")
                or (submit_data.get("data") or {}).get("task_id")
            )
            if not task_id:
                logger.error("[OpenAICompat:%s] no task_id in response: %s", self.name, submit_data)
                return None
            logger.info("[OpenAICompat:%s] video task created: %s", self.name, task_id)
        except Exception as e:
            logger.error("[OpenAICompat:%s] video submit failed: %s", self.name, e)
            return None

        # Step 2: Poll
        poll_intervals = [5, 10, 15, 20, 30]
        elapsed = 0
        poll_idx = 0
        last_status: Optional[str] = None
        video_url: Optional[str] = None

        while elapsed < 300:
            await asyncio.sleep(poll_intervals[min(poll_idx, len(poll_intervals) - 1)])
            elapsed += poll_intervals[min(poll_idx, len(poll_intervals) - 1)]
            poll_idx += 1

            try:
                async with self._client(timeout=30.0) as client:
                    resp = await client.get(
                        f"{self.base_url}/videos/generations/{task_id}",
                    )
                resp.raise_for_status()
                data = resp.json()
                last_status = (
                    data.get("status")
                    or (data.get("data") or {}).get("status")
                )
                if last_status in ("succeed", "success", "completed", "SUCCEEDED"):
                    video_url = (
                        data.get("video_url")
                        or data.get("url")
                        or (data.get("data") or {}).get("video_url")
                    )
                    if not video_url and isinstance(data.get("video"), dict):
                        video_url = data["video"].get("video_url") or data["video"].get("url")
                    break
                if last_status in ("failed", "error", "FAILED", "ERROR"):
                    logger.warning("[OpenAICompat:%s] video task failed: %s", self.name, data)
                    return None
            except Exception as e:
                logger.warning("[OpenAICompat:%s] poll error: %s", self.name, e)
                continue

        if not video_url:
            logger.warning("[OpenAICompat:%s] video timed out after %ds (status=%s)", self.name, elapsed, last_status)
            return None

        # Step 3: Download
        return await self._download_video(video_url)

    async def _download_video(self, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                cache_dir = CACHE_DIR / "videos"
                cache_dir.mkdir(parents=True, exist_ok=True)
                video_path = cache_dir / f"{uuid.uuid4().hex[:8]}.mp4"
                with open(video_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
            logger.info("[OpenAICompat:%s] downloaded video to %s", self.name, video_path)
            return str(video_path)
        except Exception as e:
            logger.warning("[OpenAICompat:%s] download failed: %s", self.name, e)
            return None
