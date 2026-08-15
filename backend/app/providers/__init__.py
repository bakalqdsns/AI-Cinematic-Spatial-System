"""
Provider registry — maps provider name → BaseProvider subclass.

Built-in providers:
  - "dashscope"          → DashScopeProvider (Alibaba Cloud official SDK)
  - "openai_compatible"  → OpenAICompatibleProvider (ToAPIs, SiliconFlow, Groq, ...)

Custom providers can be registered at runtime via register_provider(name, cls).
The frontend adds new entries purely through configuration (see ProviderConfig
in settingsService.ts) — the backend doesn't need code changes for new
OpenAI-compatible services.
"""
from __future__ import annotations

import logging
from typing import Optional, Type

from app.providers.base import BaseProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.dashscope import DashScopeProvider

logger = logging.getLogger(__name__)


_PROVIDER_REGISTRY: dict[str, Type[BaseProvider]] = {
    "openai_compatible": OpenAICompatibleProvider,
    "dashscope": DashScopeProvider,
}


def register_provider(name: str, cls: Type[BaseProvider]) -> None:
    """Register a custom BaseProvider subclass at runtime."""
    if not issubclass(cls, BaseProvider):
        raise TypeError(f"{cls} must be a subclass of BaseProvider")
    _PROVIDER_REGISTRY[name.lower()] = cls
    logger.info("[Providers] Registered: %s (%s)", name, cls.__name__)


def get_provider_class(name: str) -> Type[BaseProvider]:
    """Resolve a provider name to its class. Falls back to OpenAICompatible."""
    cls = _PROVIDER_REGISTRY.get((name or "").lower())
    if cls is None:
        logger.warning(
            "[Providers] Unknown provider %r; falling back to openai_compatible. "
            "Available: %s",
            name, list(_PROVIDER_REGISTRY.keys()),
        )
        return OpenAICompatibleProvider
    return cls


def list_providers() -> list[dict]:
    """Return metadata for all registered providers (for the Settings UI)."""
    return [
        {
            "name": name,
            "type": cls.type,
            "supports_chat": cls.supports_chat,
            "supports_vlm": cls.supports_vlm,
            "supports_image": cls.supports_image,
            "supports_video": cls.supports_video,
        }
        for name, cls in _PROVIDER_REGISTRY.items()
    ]


def instantiate(name: str, config: dict) -> BaseProvider:
    """Build a provider instance from name + config dict."""
    cls = get_provider_class(name)
    return cls(name=name, config=config or {})
