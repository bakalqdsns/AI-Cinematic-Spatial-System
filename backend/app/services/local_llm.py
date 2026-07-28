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


# ── Module-level singleton (used by services) ──────────────────────────────────

_llm_client: Optional[LocalLLMClient] = None
_use_cloud: bool = False  # Set to True in cloud mode to route through DashScopeClient


def get_llm_client() -> "LocalLLMClient | DashScopeProxy":
    """Return the shared LLM client singleton.

    When use_cloud=True, returns a proxy that delegates to DashScopeClient;
    otherwise returns the local llama-server LocalLLMClient.
    """
    global _llm_client, _use_cloud
    if _use_cloud:
        from app.services.dashscope_client import get_dashscope_client
        return DashScopeProxy(get_dashscope_client())
    if _llm_client is None:
        # Lazy import to avoid circular dependency at module load time.
        from app.config import settings as _settings
        _llm_client = LocalLLMClient(
            base_url=_settings.llm_base_url,
            model=_settings.llm_model,
            timeout=_settings.llm_timeout,
        )
    return _llm_client


def set_use_cloud(enabled: bool) -> None:
    """Toggle cloud mode. When enabled, LLM calls route through DashScopeClient."""
    global _use_cloud
    _use_cloud = enabled


def configure_llm(base_url: str, model: str, timeout: float = 600.0) -> None:
    """Reconfigure the shared local LLM client (e.g. from Settings)."""
    global _llm_client
    _llm_client = LocalLLMClient(base_url=base_url, model=model, timeout=timeout)
    logger.info("[LocalLLM] Configured: base_url=%s model=%s timeout=%.1fs", base_url, model, timeout)


class DashScopeProxy:
    """
    Drop-in proxy that wraps DashScopeClient with the same interface as LocalLLMClient.

    Allows callers that expect LocalLLMClient to transparently switch to DashScope
    by replacing the client without changing their code.

    Auto-fallback: if DashScope raises an HTTP error, switches to the local
    llama.cpp client for this request (and future requests in this process).
    """

    def __init__(self, client):
        self._client = client
        self._local_client: Optional[LocalLLMClient] = None

    def _get_local_client(self) -> LocalLLMClient:
        """Lazily build a local LLM client from current settings."""
        if self._local_client is None:
            from app.config import settings as _settings

            self._local_client = LocalLLMClient(
                base_url=_settings.llm_base_url,
                model=_settings.llm_model,
                timeout=_settings.llm_timeout,
            )
            logger.info("[DashScopeProxy] Auto-fallback: local client configured for %s/%s",
                         _settings.llm_base_url, _settings.llm_model)
        return self._local_client

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stop: Optional[list[str]] = None,
    ) -> str:
        try:
            return self._client.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            # Only attempt fallback while still in cloud mode to avoid
            # cascading switches if local also fails.
            global _use_cloud
            if not _use_cloud:
                raise

            logger.warning(
                "[DashScopeProxy] DashScope failed (%s: %s). Falling back to local LLM.",
                type(exc).__name__, exc,
            )
            # Prevent other concurrent requests from also triggering fallback.
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
            return await self.chat(
                [{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            global _use_cloud
            if not _use_cloud:
                raise

            logger.warning(
                "[DashScopeProxy] DashScope complete failed (%s: %s). Falling back to local LLM.",
                type(exc).__name__, exc,
            )
            set_use_cloud(False)
            return await self._get_local_client().complete(
                prompt, temperature=temperature, max_tokens=max_tokens,
            )

    async def is_alive(self) -> bool:
        if self._local_client is not None:
            return await self._local_client.is_alive()
        return True  # DashScope API available when no fallback has occurred
