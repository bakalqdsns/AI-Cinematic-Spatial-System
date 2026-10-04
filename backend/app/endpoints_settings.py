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
from app.providers import list_providers

_log = logging.getLogger("aicss.settings")
router = APIRouter(prefix="/api/aicss/settings", tags=["Settings"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    """Partial update payload. Any omitted field is left unchanged."""

    model_config = {"extra": "ignore"}  # Future-proofing — unknown fields silently dropped.

    model_mode: str | None = Field(None, description="Global model mode: 'cloud' | 'local'")
    vlm_mode: str | None = Field(None, description="VLM mode: 'cloud' | 'local'")
    image_mode: str | None = Field(None, description="Image generation mode: 'cloud' | 'local'")
    video_mode: str | None = Field(None, description="Video generation mode: 'cloud' | 'local'")
    llm_base_url: str | None = Field(None, description="OpenAI-compatible base URL for the local LLM server")
    llm_model: str | None = Field(None, description="Local LLM model name (e.g. 'qwen2.5-7b-q4_k_m')")
    image_model_id: str | None = Field(None, description="Diffusers model ID for local image generation")
    image_dtype: str | None = Field(None, description="Dtype for image generation: 'float16' | 'bfloat16' | 'float32'")
    video_provider: str | None = Field(None, description="Video provider: 'dashscope' | 'local_wan' | 'svd'")
    # Deprecated — kept for backwards compatibility. Use the four per-component keys below.
    dashscope_api_key: str | None = Field(None, description="[deprecated] Legacy single DashScope API key")
    # Per-component DashScope API keys (masked on read).
    dashscope_llm_api_key: str | None = Field(None, description="DashScope API key for LLM calls")
    dashscope_vlm_api_key: str | None = Field(None, description="DashScope API key for VLM (vision) calls")
    dashscope_image_api_key: str | None = Field(None, description="DashScope API key for image generation")
    dashscope_video_api_key: str | None = Field(None, description="DashScope API key for video generation")
    dashscope_llm_model: str | None = Field(None, description="DashScope LLM model ID (e.g. 'qwen-plus')")
    dashscope_vlm_model: str | None = Field(None, description="DashScope VLM model ID (e.g. 'qwen-vl-chat-v1')")
    dashscope_image_model: str | None = Field(None, description="DashScope image model ID (e.g. 'wanx-v1')")

    # ── Cloud provider selection (legacy single-field) ─────────────────────────
    cloud_llm_provider: str | None = Field(None, description="Cloud provider for LLM: 'dashscope' | 'toapi' (legacy)")
    cloud_vlm_provider: str | None = Field(None, description="Cloud provider for VLM: 'dashscope' | 'toapi' (legacy)")
    cloud_image_provider: str | None = Field(None, description="Cloud provider for image: 'dashscope' | 'toapi' (legacy)")
    cloud_video_provider: str | None = Field(None, description="Cloud provider for video: 'dashscope' | 'toapi' (legacy)")
    toapi_llm_model: str | None = Field(None, description="ToAPIs LLM model ID (legacy)")
    toapi_image_model: str | None = Field(None, description="ToAPIs image model ID (legacy)")
    toapi_video_model: str | None = Field(None, description="ToAPIs video model ID (legacy)")
    toapi_llm_api_key: str | None = Field(None, description="ToAPIs API key (legacy; shared by LLM/Image/Video)")

    # ── Unified cloud provider registry (recommended approach) ───────────────────
    # Each item: {
    #   "name": "siliconflow", "type": "openai_compatible", "base_url": "...",
    #   "api_key": "sk-xxx", "extra_headers": {...}, "extra_json": {...},
    #   "models": {"llm": "...", "vlm": "...", "image": "...", "video": "..."}
    # }
    providers: list[dict] | None = Field(None, description="User-defined cloud provider registry")


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


@router.get("/store")
async def get_settings_store() -> dict:
    """Return the location of the on-disk settings store + override count.

    Used by the frontend to show "your preferences are persisted at …" and
    to provide a "reset to defaults" button.
    """
    try:
        from app.services.settings_store import settings_file_path, load_overrides
        return {
            "path": settings_file_path(),
            "override_count": len(load_overrides()),
        }
    except Exception as exc:
        _log.warning("[settings] store lookup failed: %s", exc)
        return {"path": "", "override_count": 0, "error": str(exc)}


@router.delete("/store")
async def reset_settings_store() -> dict:
    """Delete the persisted overrides file. Runtime settings are not changed
    (use a settings update with explicit values to revert them)."""
    try:
        from app.services.settings_store import SETTINGS_FILE, save_overrides
        if SETTINGS_FILE.exists():
            SETTINGS_FILE.unlink()
        # Also re-write an empty file so subsequent loads return clean state.
        save_overrides({})
        return {"success": True, "message": "Persisted settings reset."}
    except Exception as exc:
        _log.warning("[settings] reset failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Cloud provider registry endpoints ──────────────────────────────────────────

provider_router = APIRouter(prefix="/api/aicss/providers", tags=["Cloud Providers"])


@provider_router.get("/types")
async def get_provider_types() -> list[dict]:
    """Return metadata for all registered provider types (DashScope, OpenAI-compat, ...)."""
    out = []
    for p in list_providers():
        out.append({
            "name": p["name"],
            "type": p["type"],
            "supports_chat": bool(p["supports_chat"]),
            "supports_vlm": bool(p["supports_vlm"]),
            "supports_image": bool(p["supports_image"]),
            "supports_video": bool(p["supports_video"]),
        })
    return out


class PingRequest(BaseModel):
    component: str = Field(..., description="llm | vlm | image | video")
    name: str | None = Field(None, description="Provider name override (uses current active if omitted)")


@provider_router.post("/ping")
async def ping_provider(req: PingRequest) -> dict:
    """Health-check the active cloud provider for the given component."""
    try:
        from app.providers.cloud_router import provider_is_alive
        alive = await provider_is_alive(req.component)
        return {"alive": alive}
    except Exception as exc:
        _log.warning("[providers] ping failed: %s", exc)
        return {"alive": False, "error": str(exc)}
