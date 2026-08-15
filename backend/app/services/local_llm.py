"""
Local LLM Client — llama.cpp Qwen2.5-7B-Instruct Q4_K_M GGUF

Uses llama.cpp's OpenAI-compatible /chat/completions endpoint served by llama-server.

In cloud mode (use_cloud=True), this client is not used; instead DashScope API
handles LLM requests via DashScopeClient.

Usage:
    client = LocalLLMClient()
    text = await client.chat([{"role": "user", "content": "Hello"}])
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def _record_llm_usage():
    """Record LLM usage to reset idle timer."""
    try:
        from app.services.llama_server_manager import record_usage
        record_usage()
    except Exception:
        pass


# ── Default config ──────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "http://localhost:8080/v1"
DEFAULT_MODEL = "qwen2.5-7b-q4_k_m"

# ── Global concurrency limiter ────────────────────────────────────────────────
# llama.cpp server is single-threaded by default — concurrent /v1/chat
# requests race for the inference slot and trigger 503 "Loading model"
# responses. A process-wide asyncio.Semaphore caps in-flight calls so that
# callers using asyncio.gather() queue up gracefully instead of hammering
# the server. Set to 2 to allow a small overlap (header is tiny, scenes is
# medium) without crashing single-slot llama-server instances.
_LLM_SEM: Optional[asyncio.Semaphore] = None
_LLM_CONCURRENCY = 2


def _get_llm_sem() -> asyncio.Semaphore:
    global _LLM_SEM
    if _LLM_SEM is None:
        _LLM_SEM = asyncio.Semaphore(_LLM_CONCURRENCY)
    return _LLM_SEM


class LocalLLMClient:
    """
    Thin async client for llama.cpp's OpenAI-compatible chat endpoint.

    Handles:
      - /v1/chat/completions  (primary — structured conversations)
      - /v1/completions       (fallback — raw prompt completion)
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 180.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # ── Public API ─────────────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Send a chat conversation and return the assistant's text response.

        Args:
            messages: List of {"role": "user"|"system"|"assistant", "content": str}
            temperature: Sampling temperature (0 = deterministic)
            max_tokens: Maximum new tokens to generate
            stop: Stop sequences

        Returns:
            The assistant's message content as a plain string.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                http2=False,
                trust_env=False,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ) as client:
                # Limit concurrency so the single-threaded llama.cpp server
                # doesn't get hammered with simultaneous requests.
                sem = _get_llm_sem()
                async with sem:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                    )
                resp.raise_for_status()
                data = resp.json()

            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            if not content:
                logger.warning("[LocalLLM] Empty response from server")
                return ""
            return content

        except httpx.HTTPStatusError as e:
            logger.error("[LocalLLM] HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("[LocalLLM] Connection error: %s — is llama-server running?", e)
            raise
        finally:
            _record_llm_usage()

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        Raw prompt completion (no chat template).
        Used as fallback when chat endpoint is unavailable.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                http2=False,
                trust_env=False,
            ) as client:
                resp = await client.post(
                    f"{self.base_url}/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
            return data.get("choices", [{}])[0].get("text", "")
        except httpx.HTTPStatusError as e:
            logger.error("[LocalLLM] Completion HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("[LocalLLM] Completion connection error: %s", e)
            raise
        finally:
            _record_llm_usage()

    async def is_alive(self) -> bool:
        """Ping the server's model list endpoint to check connectivity."""
        try:
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False


# ── ToAPIs client (kept for backward-compat; new code uses CloudRouter) ────────
# https://docs.toapis.com — mirrors the /v1/chat/completions interface.


class ToAPIClient:
    """
    Async client for ToAPIs' OpenAI-compatible chat API.

    Usage:
        client = ToAPIClient(api_key="your-toapis-key")
        text = await client.chat([{"role": "user", "content": "Hello"}])

    Compatible models: gpt-5.6-terra, gpt-image-2, sora-2-vvip, etc.
    """

    BASE_URL = "https://toapis.com/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.6-terra",
        base_url: str = BASE_URL,
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            payload["stop"] = stop

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                http2=False,
                trust_env=False,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            ) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            if not content:
                logger.warning("[ToAPIClient] Empty response")
                return ""
            return content
        except httpx.HTTPStatusError as e:
            logger.error("[ToAPIClient] HTTP %d: %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("[ToAPIClient] Connection error: %s", e)
            raise

    async def is_alive(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False


# ── Module-level singleton (used by services) ──────────────────────────────────

import contextvars as _contextvars
from enum import Enum as _Enum

class LLMMode(str, _Enum):
    """Mode of LLM dispatch — Phase 1.4.2 deliverable.

    CLOUD routes through DashScope / ToAPIs / any user-defined provider.
    LOCAL routes through llama.cpp (llama-server).

    The previous implementation used a module-level ``_use_cloud: bool``
    flag which any process-global mutation could clobber. We now expose
    a ``ContextVar`` so callers can opt in to per-call dispatch semantics
    (e.g. one async task wants local for testing while the rest of the
    server stays on cloud). The module-level flag is kept for backward
    compatibility — ``set_use_cloud()`` still writes both.
    """
    CLOUD = "cloud"
    LOCAL = "local"


# Per-task context — when unset, falls back to the module-level
# ``_use_cloud`` value (which mirrors ``settings.model_mode``).
_llm_mode_ctx: _contextvars.ContextVar[LLMMode] = _contextvars.ContextVar(
    "llm_mode", default=None  # type: ignore[arg-type]
)

_llm_client: Optional[LocalLLMClient] = None
_toapi_client: Optional[ToAPIClient] = None
_use_cloud: bool = False
_cloud_provider: str = "dashscope"  # "dashscope" | "toapi"


def _resolve_llm_mode() -> LLMMode:
    """Return the effective LLM mode — context overrides module default."""
    ctx_value = _llm_mode_ctx.get()
    if ctx_value is not None:
        return ctx_value
    return LLMMode.CLOUD if _use_cloud else LLMMode.LOCAL


def llm_mode_scope(mode: LLMMode):
    """Context manager — run a block of code with a specific LLM mode.

    Replaces the implicit module-level state with explicit, scoped
    dispatch. Example::

        with llm_mode_scope(LLMMode.LOCAL):
            text = await client.chat(...)

    Useful for tests (force local even when global mode is cloud) and
    for one-off calls that need a different mode than the default.

    Internally uses ``contextvars.ContextVar.set()`` which returns a
    Token (not a context manager), so we wrap the token's reset
    semantics in a small ``_LLMModeScope`` helper that implements
    ``__enter__`` / ``__exit__``.
    """
    return _LLMModeScope(mode)


class _LLMModeScope:
    """Thin context-manager wrapper around ``ContextVar.set()``.

    ``set()`` returns a Token that knows how to restore the previous
    value via ``reset()``. Implementing the context-manager protocol
    ourselves lets ``with llm_mode_scope(...):`` work in user code.
    """
    __slots__ = ("_token",)

    def __init__(self, mode: LLMMode):
        self._token = _llm_mode_ctx.set(mode)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _llm_mode_ctx.reset(self._token)
        return False


def get_llm_mode() -> LLMMode:
    """Return the current effective LLM mode (context-aware)."""
    return _resolve_llm_mode()


def get_llm_client() -> "LocalLLMClient | CloudRouterProxy":
    """Return the shared LLM client singleton.

    Dispatch rule:
      - If the current ``LLMMode`` is ``CLOUD``, return ``CloudRouterProxy``
        (which routes through the unified CloudRouter).
      - Otherwise return the local ``LocalLLMClient``.

    The mode is read from the ``_llm_mode_ctx`` ContextVar when set,
    falling back to the module-level ``_use_cloud`` flag (which mirrors
    ``settings.model_mode``). Callers that want per-task dispatch should
    use ``llm_mode_scope`` rather than mutating the global flag.
    """
    global _llm_client
    mode = _resolve_llm_mode()
    if mode == LLMMode.CLOUD:
        return CloudRouterProxy()
    if _llm_client is None:
        from app.config import settings as _settings
        _llm_client = LocalLLMClient(
            base_url=_settings.llm_base_url,
            model=_settings.llm_model,
            timeout=_settings.llm_timeout,
        )
    return _llm_client


def configure_toapi_client(api_key: str, model: str, timeout: float) -> None:
    """DEPRECATED: kept for backwards-compat. The CloudRouter now picks up
    these values automatically on the next call. Triggers a cache invalidation
    so the new credentials take effect immediately.
    """
    from app.providers.cloud_router import invalidate_cache
    invalidate_cache("llm")
    logger.info("[LocalLLM] ToAPI client config refresh requested: model=%s", model)


def set_use_cloud(enabled: bool) -> None:
    """Toggle cloud mode. When enabled, LLM calls route through DashScopeClient or ToAPIClient."""
    global _use_cloud
    _use_cloud = enabled


def set_cloud_provider(provider: str) -> None:
    """Set which cloud provider to use. Legacy entrypoint — sets the
    `cloud_llm_provider` field on settings so the CloudRouter sees it.
    Also invalidates the router cache so the change takes effect immediately.
    """
    from app.config import settings as _settings
    _settings.cloud_llm_provider = provider
    from app.providers.cloud_router import invalidate_cache
    invalidate_cache("llm")
    logger.info("[LocalLLM] Cloud provider set to: %s", provider)


def configure_llm(base_url: str, model: str, timeout: float = 600.0) -> None:
    """Reconfigure the shared local LLM client (e.g. from Settings)."""
    global _llm_client
    _llm_client = LocalLLMClient(base_url=base_url, model=model, timeout=timeout)
    logger.info("[LocalLLM] Configured: base_url=%s model=%s timeout=%.1fs", base_url, model, timeout)


# (Legacy ToAPIProxy class removed — CloudRouterProxy (defined below) replaces it.)


class CloudRouterProxy:
    """
    Drop-in proxy for the unified CloudRouter.

    Routes through `app.providers.cloud_router` (DashScope, ToAPIs, any custom
    OpenAI-compatible provider). On failure, falls back to local llama-server
    for this request and disables cloud mode for subsequent ones — matching
    the previous DashScopeProxy/ToAPIProxy behaviour.

    Replaces the legacy DashScopeProxy + ToAPIProxy pair with a single class.
    """

    def __init__(self):
        self._local_client: Optional[LocalLLMClient] = None

    def _get_local_client(self) -> LocalLLMClient:
        if self._local_client is None:
            from app.config import settings as _settings
            self._local_client = LocalLLMClient(
                base_url=_settings.llm_base_url,
                model=_settings.llm_model,
                timeout=_settings.llm_timeout,
            )
            logger.info(
                "[CloudRouterProxy] Auto-fallback: local client configured for %s/%s",
                _settings.llm_base_url, _settings.llm_model,
            )
        return self._local_client

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
    ) -> str:
        try:
            from app.providers.cloud_router import cloud_chat
            return await cloud_chat(
                messages, component="llm",
                temperature=temperature, max_tokens=max_tokens, stop=stop,
            )
        except Exception as exc:
            global _use_cloud
            if not _use_cloud:
                raise
            logger.warning(
                "[CloudRouterProxy] Cloud LLM failed (%s: %s). Falling back to local LLM.",
                type(exc).__name__, exc,
            )
            set_use_cloud(False)
            return await self._get_local_client().chat(
                messages, temperature=temperature, max_tokens=max_tokens,
            )

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
    ) -> str:
        try:
            from app.providers.cloud_router import cloud_complete
            return await cloud_complete(
                prompt, component="llm",
                temperature=temperature, max_tokens=max_tokens, stop=stop,
            )
        except Exception as exc:
            global _use_cloud
            if not _use_cloud:
                raise
            logger.warning(
                "[CloudRouterProxy] Cloud complete failed (%s: %s). Falling back to local LLM.",
                type(exc).__name__, exc,
            )
            set_use_cloud(False)
            return await self._get_local_client().complete(
                prompt, temperature=temperature, max_tokens=max_tokens,
            )

    async def is_alive(self) -> bool:
        if self._local_client is not None:
            return await self._local_client.is_alive()
        try:
            from app.providers.cloud_router import provider_is_alive
            return await provider_is_alive("llm")
        except Exception:
            return True


# Backward-compat aliases (kept so older imports don't break)
class DashScopeProxy(CloudRouterProxy):
    """DEPRECATED: alias for CloudRouterProxy (kept for backwards compat)."""
    def __init__(self, client=None):
        super().__init__()


class ToAPIProxy(CloudRouterProxy):
    """DEPRECATED: alias for CloudRouterProxy (kept for backwards compat)."""
    def __init__(self, client=None):
        super().__init__()
