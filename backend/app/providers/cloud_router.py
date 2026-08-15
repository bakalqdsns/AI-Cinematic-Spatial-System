"""
CloudRouter — single dispatch entry point for all cloud AI capabilities.

This module is the user-facing API for cloud calls. Callers don't import
DashScope or OpenAI clients directly — they import `cloud_router` and call
one of: cloud_chat, cloud_vlm_analyze, cloud_generate_image, cloud_generate_video.

The router:
  1. Reads which provider to use for each component (LLM/VLM/Image/Video) from
     the runtime settings (configured via Settings UI).
  2. Reads the model ID for that provider.
  3. Instantiates the BaseProvider subclass on demand (cached per (component, name)).
  4. Delegates the call.

Adding a new cloud model = new entry in the `providers` map in settings; NO
backend code changes required for OpenAI-compatible services.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.providers import instantiate, register_provider, list_providers
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


# ── Per-component provider cache ────────────────────────────────────────────────
# Key: (component, provider_name) → BaseProvider instance
_provider_cache: dict[tuple[str, str], BaseProvider] = {}


def _get_provider_for_component(component: str) -> BaseProvider:
    """
    Look up the BaseProvider instance for the given component (llm|vlm|image|video).

    Reads the component's current provider config from settings; instantiates the
    provider on first use and caches it for subsequent calls.
    """
    from app.config import settings

    cfg = settings.get_provider_config(component)
    name = cfg["provider"]
    cache_key = (component, name)

    cached = _provider_cache.get(cache_key)
    if cached is not None:
        # Update api_key/base_url live without rebuilding (cheap hot reload)
        cached.api_key = cfg.get("api_key") or cached.api_key
        if cfg.get("base_url"):
            cached.base_url = cfg["base_url"].rstrip("/")
        cached.config = cfg
        return cached

    inst = instantiate(name, cfg)
    _provider_cache[cache_key] = inst
    logger.info("[CloudRouter] cached %s provider: %s", component, name)
    return inst


def invalidate_cache(component: Optional[str] = None) -> None:
    """
    Clear the provider cache so the next call rebuilds from current settings.

    Called by settings_manager after a hot-reload. If `component` is None,
    clears all.
    """
    global _provider_cache
    if component is None:
        _provider_cache = {}
    else:
        _provider_cache = {
            k: v for k, v in _provider_cache.items() if k[0] != component
        }


def get_model_id(component: str) -> str:
    """Return the model ID for the given component from current settings."""
    from app.config import settings
    return settings.get_model_id(component)


# ── Public dispatch API ────────────────────────────────────────────────────────

async def cloud_chat(
    messages: list[dict],
    component: str = "llm",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    **kwargs,
) -> str:
    """Dispatch a chat completion through the component's active cloud provider."""
    provider = _get_provider_for_component(component)
    model = get_model_id(component)
    return await provider.chat(
        messages, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs,
    )


async def cloud_complete(
    prompt: str,
    component: str = "llm",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    **kwargs,
) -> str:
    """Raw completion (default implementation routes through chat)."""
    provider = _get_provider_for_component(component)
    model = get_model_id(component)
    return await provider.complete(
        prompt, model=model, temperature=temperature, max_tokens=max_tokens, **kwargs,
    )


async def cloud_vlm_analyze(
    image: str,
    prompt: str,
    **kwargs,
) -> str:
    """Vision-language analysis through the active VLM cloud provider."""
    provider = _get_provider_for_component("vlm")
    model = get_model_id("vlm")
    return await provider.vlm_analyze(image, prompt, model=model, **kwargs)


async def cloud_generate_image(
    prompt: str,
    size: str = "1024*1024",
    n: int = 1,
    **kwargs,
) -> list[str]:
    """Image generation through the active image cloud provider."""
    provider = _get_provider_for_component("image")
    model = get_model_id("image")
    return await provider.generate_image(prompt, model=model, size=size, n=n, **kwargs)


async def cloud_generate_video(
    prompt: str,
    start_image_b64: Optional[str] = None,
    end_image_b64: Optional[str] = None,
    duration: float = 5.0,
    **kwargs,
) -> Optional[str]:
    """Video generation through the active video cloud provider."""
    provider = _get_provider_for_component("video")
    model = get_model_id("video")
    return await provider.generate_video(
        prompt,
        model=model,
        start_image_b64=start_image_b64,
        end_image_b64=end_image_b64,
        duration=duration,
        **kwargs,
    )


async def provider_is_alive(component: str = "llm") -> bool:
    """Health check for the active provider of a component."""
    try:
        provider = _get_provider_for_component(component)
        return await provider.is_alive()
    except Exception as e:
        logger.warning("[CloudRouter] is_alive check failed: %s", e)
        return False


__all__ = [
    "cloud_chat",
    "cloud_complete",
    "cloud_vlm_analyze",
    "cloud_generate_image",
    "cloud_generate_video",
    "provider_is_alive",
    "invalidate_cache",
    "register_provider",
    "list_providers",
]
