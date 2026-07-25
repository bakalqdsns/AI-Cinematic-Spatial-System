"""
Settings HTTP endpoints.

  GET  /api/aicss/settings — return current runtime settings
  POST /api/aicss/settings — partial update, returns the new snapshot

Sensitive fields (e.g. DashScope API key) are masked on read; the full value
must be sent again on write to change it.
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import settings_manager

_log = logging.getLogger("aicss.settings")
router = APIRouter(prefix="/api/aicss/settings", tags=["Settings"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    """Partial update payload. Any omitted field is left unchanged."""

    llm_base_url: str | None = Field(None, description="OpenAI-compatible base URL for the local LLM server")
    llm_model: str | None = Field(None, description="Model name (e.g. 'qwen3.5-9b')")
    image_model_id: str | None = Field(None, description="Diffusers model ID for local image generation")
    image_dtype: str | None = Field(None, description="Dtype for image generation: 'float16' | 'bfloat16' | 'float32'")
    video_provider: str | None = Field(None, description="Video provider: 'dashscope' | 'local_wan' | 'svd'")
    dashscope_api_key: str | None = Field(None, description="DashScope API key (used for inpainting / remote video)")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
@router.get("/")
async def get_settings() -> dict:
    """Return the current runtime settings (sensitive fields masked)."""
    return settings_manager.get_settings()


@router.post("")
@router.post("/")
async def post_settings(payload: SettingsUpdate) -> dict:
    """Apply a partial update and return the new settings snapshot."""
    updates: dict[str, Any] = {
        k: v for k, v in payload.model_dump().items() if v is not None
    }
    if not updates:
        return settings_manager.get_settings()

    try:
        return settings_manager.update_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        _log.exception("[settings] update failed")
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {exc}")
