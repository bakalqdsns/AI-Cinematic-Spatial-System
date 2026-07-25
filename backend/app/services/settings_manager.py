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
    "llm_base_url",
    "llm_model",
    "image_model_id",
    "image_dtype",
    "video_provider",
    "dashscope_api_key",
)

# API keys are sensitive; we redact them in GET responses.
SENSITIVE_FIELDS = ("dashscope_api_key",)


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
