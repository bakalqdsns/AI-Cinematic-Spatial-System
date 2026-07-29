"""
Runtime settings manager — exposes a mutable subset of `config.settings` via
the `/api/aicss/settings` HTTP endpoint so the frontend can switch models
without restarting the backend.

We deliberately keep only fields that:
  1. Are safe to swap at runtime (e.g. URLs, model IDs, dtypes, providers).
  2. Have a hot-reload path already wired into the service singletons
     (`configure_llm`, `configure_image_generator`).

Values not exposed here (depth/detection/sam2/VLM checkpoints, device, etc.)
are intentionally left alone — they are slower / heavier to reload and rarely
need to change after startup.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings

_log = logging.getLogger("aicss.settings")


# Fields that are visible to the frontend and safe to mutate at runtime.
# Anything outside this list is server-side only and read-only through the API.
RUNTIME_FIELDS = (
    "model_mode",
    "vlm_mode",
    "image_mode",
    "video_mode",
    "dashscope_llm_model",
    "dashscope_vlm_model",
    "dashscope_image_model",
    "llm_base_url",
    "llm_model",
    "image_model_id",
    "image_dtype",
    "video_provider",
    "dashscope_llm_api_key",
    "dashscope_vlm_api_key",
    "dashscope_image_api_key",
    "dashscope_video_api_key",
)

# API keys are sensitive; we redact them in GET responses.
SENSITIVE_FIELDS = (
    "dashscope_llm_api_key",
    "dashscope_vlm_api_key",
    "dashscope_image_api_key",
    "dashscope_video_api_key",
)


def _resolve_api_key(component_key: str) -> str:
    """Resolve the API key for a given DashScope component.

    Order of precedence:
      1. The per-component field set via the Settings UI.
      2. The generic ``DASHSCOPE_API_KEY`` env var (covers legacy deployments).
      3. Empty string — caller will surface a clear "missing key" error.
    """
    from app.config import settings as _settings
    val = getattr(_settings, component_key, "")
    if val:
        return val
    return os.getenv("DASHSCOPE_API_KEY", "")


def _coerce_value(key: str, value: Any) -> Any:
    """Apply light type coercion so the API tolerates JSON-friendly inputs."""
    if key in ("llm_timeout",) and value is not None:
        # llm_timeout isn't in RUNTIME_FIELDS but keep coercion available
        return float(value)
    return value


def get_settings() -> dict:
    """Return the current runtime settings. Sensitive fields are masked."""
    result: dict[str, Any] = {}
    for key in RUNTIME_FIELDS:
        value = getattr(settings, key, None)
        if key in SENSITIVE_FIELDS and value:
            value = "***"
        result[key] = value
    return result


def update_settings(updates: dict) -> dict:
    """
    Apply a partial update to runtime settings, then trigger hot-reload where
    appropriate. Returns the (post-update) runtime settings snapshot.

    Unknown keys are silently ignored so the API is forward-compatible.
    """
    if not isinstance(updates, dict):
        raise ValueError("settings update must be a JSON object")

    changes: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in RUNTIME_FIELDS:
            continue
        coerced = _coerce_value(key, value)
        # Skip no-op writes to avoid spurious reloads.
        current = getattr(settings, key, None)
        if coerced == current:
            continue
        setattr(settings, key, coerced)
        changes[key] = coerced

    if not changes:
        _log.info("[settings] update called, no effective changes")
        return get_settings()

    _log.info("[settings] applying changes: %s", sorted(changes.keys()))

    # ── Hot-reload model mode ───────────────────────────────────────────────
    if "model_mode" in changes:
        new_mode = changes["model_mode"]
        cloud = new_mode == "cloud"
        try:
            from app.services.local_llm import set_use_cloud
            set_use_cloud(cloud)
            _log.info("[settings] Model mode switched to: %s", new_mode)
        except Exception as exc:
            _log.warning("[settings] Model mode switch failed: %s", exc)

        # ── Auto-start/stop llama-server when switching to/from local ───────
        if not cloud:
            # User selected local LLM — start llama-server if not already running
            try:
                from app.services.llama_server_manager import start_server, health_check
                import asyncio
                import threading

                async def _start_async():
                    if not await health_check():
                        result = await start_server()
                        if result["success"]:
                            _log.info("[settings] llama-server auto-started for local LLM: %s", result["message"])
                        else:
                            _log.warning("[settings] llama-server auto-start failed: %s", result["message"])
                    else:
                        _log.info("[settings] llama-server already running, skipping start")

                # Run async start in background thread so we don't block the sync
                # settings endpoint response.  The thread starts its own event loop.
                def _run_start():
                    asyncio.run(_start_async())

                threading.Thread(target=_run_start, daemon=True, name="llama-auto-start").start()
            except Exception as exc:
                _log.warning("[settings] Failed to trigger llama-server auto-start: %s", exc)

    # ── Hot-reload per-component modes (vlm, image, video) ──────────────────
    for mode_key in ("vlm_mode", "image_mode", "video_mode"):
        if mode_key in changes:
            new_mode = changes[mode_key]
            _log.info("[settings] %s switched to: %s", mode_key, new_mode)
            # Per-component mode switches can be handled by respective services
            # as needed (e.g., configure_vlm, configure_image_gen, configure_video)

    # ── video_mode → defaults video_provider ─────────────────────────────────
    # When the user toggles video_mode, auto-set a sensible video_provider default
    # so the dropdown always shows a valid selected value.
    if "video_mode" in changes:
        _mode = changes["video_mode"]
        _cur_provider = getattr(_cfg, "video_provider", "dashscope")
        if _mode == "cloud" and _cur_provider not in ("dashscope", "local_wan", "svd"):
            _cfg.video_provider = "dashscope"
            _log.info("[settings] video_provider auto-set to 'dashscope' (video_mode=cloud)")
        elif _mode == "local" and _cur_provider == "dashscope":
            _cfg.video_provider = "local_wan"
            _log.info("[settings] video_provider auto-set to 'local_wan' (video_mode=local)")

    # ── Hot-reload DashScope client ─────────────────────────────────────────
    if "dashscope_llm_model" in changes or "dashscope_vlm_model" in changes or "dashscope_image_model" in changes:
        try:
            from app.services.dashscope_client import configure_dashscope_client
            configure_dashscope_client(
                llm_model=changes.get("dashscope_llm_model") or None,
                vlm_model=changes.get("dashscope_vlm_model") or None,
                image_model=changes.get("dashscope_image_model") or None,
            )
            updated_keys = [k for k in ("dashscope_llm_model", "dashscope_vlm_model", "dashscope_image_model") if k in changes]
            _log.info("[settings] DashScope models updated: %s", updated_keys)
        except Exception as exc:
            _log.warning("[settings] DashScope reconfigure failed: %s", exc)

    # ── Hot-reload per-component DashScope API keys ─────────────────────────
    api_key_changes = {
        k: v for k, v in changes.items()
        if k in SENSITIVE_FIELDS and isinstance(v, str) and v
    }
    if api_key_changes:
        # Mirror to process env so the dashscope SDK (which reads DASHSCOPE_API_KEY
        # at call time) and any subprocesses spawned later (e.g. llama-server,
        # dashscope video adapter) all see the latest key without restart.
        for k, v in api_key_changes.items():
            os.environ[k.upper()] = v
            _log.info("[settings] DashScope API key updated: %s (len=%d)", k, len(v))
        # Force-reset dashscope.api_key if any component key changed so the SDK
        # re-reads it on the next call. Setting an empty string clears the cached
        # key, forcing Generation.call / MultiModalConversation.call / etc. to
        # re-resolve via the env var.
        try:
            import dashscope as _dashscope
            _dashscope.api_key = ""
        except Exception:
            pass

    # ── Hot-reload LLM client ──────────────────────────────────────────────
    if "llm_base_url" in changes or "llm_model" in changes:
        try:
            from app.services.local_llm import configure_llm
            configure_llm(
                base_url=settings.llm_base_url,
                model=settings.llm_model,
            )
            _log.info(
                "[settings] LLM client reconfigured: base_url=%s model=%s",
                settings.llm_base_url, settings.llm_model,
            )
        except Exception as exc:
            _log.warning("[settings] LLM reconfigure failed: %s", exc)

    # ── Hot-reload image generator ─────────────────────────────────────────
    if "image_model_id" in changes or "image_dtype" in changes:
        try:
            from app.services.image_generator import configure_image_generator
            configure_image_generator(
                model_id=settings.image_model_id,
                dtype_name=settings.image_dtype,
            )
            _log.info(
                "[settings] Image generator reconfigured: model=%s dtype=%s",
                settings.image_model_id, settings.image_dtype,
            )
        except Exception as exc:
            _log.warning("[settings] Image generator reconfigure failed: %s", exc)

    # ── Persist non-secret runtime values to process env so child processes
    # (e.g. llama-server Popen) created later in the same session also see
    # them. AICSS_ prefix matches `Settings.Config.env_prefix`.
    for key, value in changes.items():
        if key in SENSITIVE_FIELDS:
            continue
        if value is None:
            continue
        os.environ[f"AICSS_{key.upper()}"] = str(value)

    return get_settings()
