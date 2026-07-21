"""
Local LLM Client — llama.cpp Qwen3.5-9B-GGUF

Uses llama.cpp's OpenAI-compatible /chat/completions endpoint served by llama-server.
No GPU VRAM required for the inference server itself (llama.cpp handles quantization).

Usage:
    # Start the server (one-time, keep running):
    #   llama-server -hf lmstudio-community/Qwen3.5-9B-GGUF:Q4_K_M \\
    #       -c 8192 --host 0.0.0.0 --port 8080

    client = LocalLLMClient()
    text = await client.chat([{"role": "user", "content": "Hello"}])
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Default config ──────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "http://localhost:8080/v1"
DEFAULT_MODEL = "qwen3.5-9b"


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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            if not content:
                # Fallback to usage-based check
                logger.warning("[LocalLLM] Empty response from server")
                return ""
            return content

        except httpx.HTTPStatusError as e:
            logger.error("[LocalLLM] HTTP error %d: %s", e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("[LocalLLM] Connection error: %s — is llama-server running?", e)
            raise

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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
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

    async def is_alive(self) -> bool:
        """Ping the server's model list endpoint to check connectivity."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False


# ── Module-level singleton (used by services) ──────────────────────────────────

_llm_client: Optional[LocalLLMClient] = None


def get_llm_client() -> LocalLLMClient:
    """Return the shared LocalLLMClient singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LocalLLMClient()
    return _llm_client


def configure_llm(base_url: str, model: str) -> None:
    """Reconfigure the shared client (e.g. from Settings)."""
    global _llm_client
    _llm_client = LocalLLMClient(base_url=base_url, model=model)
    logger.info("[LocalLLM] Configured: base_url=%s model=%s", base_url, model)
