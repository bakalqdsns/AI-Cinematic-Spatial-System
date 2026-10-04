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
import threading
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
    # Per-component cloud provider: "dashscope" | "toapi" (legacy) or any user-defined
    "cloud_llm_provider",
    "cloud_vlm_provider",
    "cloud_image_provider",
    "cloud_video_provider",
    # ToAPIs model IDs (legacy per-component fields)
    "toapi_llm_model",
    "toapi_image_model",
    "toapi_video_model",
    # DashScope model IDs
    "dashscope_llm_model",
    "dashscope_vlm_model",
    "dashscope_image_model",
    # Local LLM
    "llm_base_url",
    "llm_model",
    # Local Image
    "image_model_id",
    "image_dtype",
    # Video
    "video_provider",
    "motion_greenscreen_default",
    "motion_feather_edges_default",
    # API keys
    "dashscope_llm_api_key",
    "dashscope_vlm_api_key",
    "dashscope_image_api_key",
    "dashscope_video_api_key",
    "toapi_llm_api_key",
    # Unified provider registry (the new approach; supersedes all of the above)
    "providers",
)

# API keys are sensitive; we redact them in GET responses.
SENSITIVE_FIELDS = (
    "dashscope_llm_api_key",
    "dashscope_vlm_api_key",
    "dashscope_image_api_key",
    "dashscope_video_api_key",
    "toapi_llm_api_key",
)


# ── Runtime values store ───────────────────────────────────────────────────────
# `_runtime_values` is the single source of truth for runtime settings. It is
# seeded lazily from `config.settings` defaults on first access (or explicitly
# during the `lifespan` startup hook) and updated by `update_settings()`.
# Consumers should read via `settings_manager.get(key)` rather than
# `from app.config import settings; settings.<key>` so they observe live
# updates without `config.settings` being mutated.
#
# This breaks the previous D-level content coupling where `update_settings()`
# did `setattr(settings, key, value)` directly on the global singleton. The
# `config.settings` instance is now treated as an immutable startup default
# source only — its fields are never written after initialization.
_runtime_values: dict[str, Any] = {}
_runtime_initialized: bool = False
_runtime_lock = threading.RLock()


def _ensure_initialized() -> None:
    """Seed `_runtime_values` from `config.settings` defaults on first call.

    Idempotent and thread-safe. Subsequent calls are no-ops. After seeding,
    `_runtime_values` holds a snapshot of every `RUNTIME_FIELDS` entry as it
    was at startup (possibly overridden by `seed_overrides()` from disk).
    """
    global _runtime_initialized
    if _runtime_initialized:
        return
    with _runtime_lock:
        if _runtime_initialized:
            return
        for key in RUNTIME_FIELDS:
            _runtime_values[key] = getattr(settings, key, None)
        _runtime_initialized = True


def get(key: str, default: Any = None) -> Any:
    """Read a runtime setting by key.

    Lookup order:
      1. `_runtime_values` (the live runtime source of truth).
      2. `getattr(settings, key, default)` — compatibility fallback for
         fields outside `RUNTIME_FIELDS` (e.g. `image_checkpoint_dir`,
         `llm_timeout`) that are still defined on `Settings` but never
         hot-reloaded.

    Consumers should always go through this function (or
    `settings_manager.get_settings()`) instead of importing `config.settings`
    directly, so they observe hot-reloaded values without the global
    singleton being mutated.
    """
    _ensure_initialized()
    if key in _runtime_values:
        return _runtime_values[key]
    return getattr(settings, key, default)


def set_runtime_value(key: str, value: Any) -> None:
    """Write a runtime value directly, bypassing observers and hot-reload.

    Used by internal cascade observers (e.g. `ModelModeCascadeObserver`) that
    need to update dependent settings without re-entering `update_settings()`.
    External callers should use `update_settings()` instead.
    """
    _ensure_initialized()
    with _runtime_lock:
        _runtime_values[key] = value


def seed_overrides(overrides: dict) -> int:
    """Apply persisted user overrides at startup without triggering observers.

    Called by `settings_store.apply_overrides()` during the `lifespan` startup
    hook. Returns the number of overrides that actually changed a value.
    """
    _ensure_initialized()
    applied = 0
    with _runtime_lock:
        for key, value in overrides.items():
            if key not in RUNTIME_FIELDS:
                continue
            if _runtime_values.get(key) == value:
                continue
            _runtime_values[key] = value
            applied += 1
    return applied


def _resolve_api_key(component_key: str) -> str:
    """Resolve the API key for a given DashScope component.

    Order of precedence:
      1. The per-component field set via the Settings UI (read from the
         runtime values store so hot-reloaded keys take effect immediately).
      2. The generic ``DASHSCOPE_API_KEY`` env var (covers legacy deployments).
      3. Empty string — caller will surface a clear "missing key" error.
    """
    val = get(component_key, "")
    if val:
        return str(val)
    return os.getenv("DASHSCOPE_API_KEY", "")


def _coerce_value(key: str, value: Any) -> Any:
    """Apply light type coercion so the API tolerates JSON-friendly inputs."""
    if key in ("llm_timeout",) and value is not None:
        # llm_timeout isn't in RUNTIME_FIELDS but keep coercion available
        return float(value)
    if key in ("motion_greenscreen_default", "motion_feather_edges_default"):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        if value is None:
            return False
        return bool(value)
    return value


def get_settings() -> dict:
    """Return the current runtime settings. Sensitive fields are masked."""
    _ensure_initialized()
    result: dict[str, Any] = {}
    for key in RUNTIME_FIELDS:
        value = _runtime_values.get(key, getattr(settings, key, None))
        if key in SENSITIVE_FIELDS and value:
            value = "***"
        if key == "providers" and isinstance(value, list):
            # Mask api_key fields inside each provider entry
            masked = []
            for p in value:
                pp = dict(p) if isinstance(p, dict) else p
                if isinstance(pp, dict) and pp.get("api_key"):
                    pp["api_key"] = "***"
                masked.append(pp)
            value = masked
        result[key] = value
    return result


def update_settings(updates: dict) -> dict:
    """
    Apply a partial update to runtime settings, then trigger hot-reload where
    appropriate. Returns the (post-update) runtime settings snapshot.

    Unknown keys are silently ignored so the API is forward-compatible.

    State is held in the module-level `_runtime_values` dict — `config.settings`
    is no longer mutated. Observers registered via
    ``services.settings_observer.register_observer`` are notified of each
    effective change so consumers (LLM, ImageGen, CloudRouter) can react
    without polling any global singleton.
    """
    if not isinstance(updates, dict):
        raise ValueError("settings update must be a JSON object")

    _ensure_initialized()
    changes: dict[str, Any] = {}
    previous: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in RUNTIME_FIELDS:
            continue
        coerced = _coerce_value(key, value)
        # Skip no-op writes to avoid spurious reloads.
        current = _runtime_values.get(key, getattr(settings, key, None))
        if coerced == current:
            continue
        previous[key] = current
        _runtime_values[key] = coerced
        changes[key] = coerced

    if not changes:
        _log.info("[settings] update called, no effective changes")
        return get_settings()

    _log.info("[settings] applying changes: %s", sorted(changes.keys()))

    # ── Notify observers (Phase 1.4.1) ───────────────────────────────────────
    # Fan out each change so consumers can react. Wrapped in try/except so
    # a buggy observer can never break the hot-reload chain.
    try:
        from app.services.settings_observer import notify_bulk
        notify_bulk(changes, previous)
    except Exception as exc:
        _log.warning("[settings] observer notification failed: %s", exc)

    # ── Hot-reload cloud providers ─────────────────────────────────────────────
    provider_fields = {
        "cloud_llm_provider": "llm",
        "cloud_vlm_provider": "vlm",
        "cloud_image_provider": "image",
        "cloud_video_provider": "video",
    }
    if any(k in changes for k in provider_fields) or "providers" in changes:
        try:
            from app.providers.cloud_router import invalidate_cache

            if "cloud_llm_provider" in changes:
                _log.info(
                    "[settings] Cloud LLM provider switched to: %s",
                    changes["cloud_llm_provider"],
                )

            # Invalidate the cache for every affected component so the router
            # rebuilds providers from the new settings on the next call.
            for field, comp in provider_fields.items():
                if field in changes:
                    invalidate_cache(comp)
            if "providers" in changes:
                invalidate_cache()  # full reset
                _log.info(
                    "[settings] Providers registry updated: %d entries",
                    len(get("providers") or []),
                )
        except Exception as exc:
            _log.warning("[settings] Cloud provider switch failed: %s", exc)

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
        _cur_provider = get("video_provider", "dashscope")
        if _mode == "cloud" and _cur_provider not in ("dashscope", "local_wan", "svd"):
            set_runtime_value("video_provider", "dashscope")
            _log.info("[settings] video_provider auto-set to 'dashscope' (video_mode=cloud)")
        elif _mode == "local" and _cur_provider == "dashscope":
            set_runtime_value("video_provider", "local_wan")
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

    # ── Hot-reload per-component API keys ───────────────────────────────────
    api_key_changes = {
        k: v for k, v in changes.items()
        if k in SENSITIVE_FIELDS and isinstance(v, str) and v
    }
    if api_key_changes:
        # Mirror to process env so callers that read env vars at call time
        # (DashScope SDK, OpenAI-compat provider) see the latest key without
        # restart. The CloudRouter picks these up via settings on next call.
        for k, v in api_key_changes.items():
            os.environ[k.upper()] = v
            _log.info("[settings] API key updated: %s (len=%d)", k, len(v))

        # DashScope SDK caches the key globally; clear it so the SDK re-reads
        # from the env (or from our explicit api_key= kwarg) on next call.
        if any(k.startswith("dashscope") for k in api_key_changes):
            try:
                import dashscope as _dashscope
                _dashscope.api_key = ""
            except Exception:
                pass

        # Any API-key change → invalidate the CloudRouter cache so the next
        # request rebuilds the provider with the new credentials.
        try:
            from app.providers.cloud_router import invalidate_cache
            invalidate_cache()
        except Exception:
            pass

    # ── Hot-reload LLM client ──────────────────────────────────────────────
    if "llm_base_url" in changes or "llm_model" in changes:
        try:
            from app.services.local_llm import configure_llm
            configure_llm(
                base_url=get("llm_base_url"),
                model=get("llm_model"),
            )
            _log.info(
                "[settings] LLM client reconfigured: base_url=%s model=%s",
                get("llm_base_url"), get("llm_model"),
            )
        except Exception as exc:
            _log.warning("[settings] LLM reconfigure failed: %s", exc)

    # ── Hot-reload image generator ─────────────────────────────────────────
    if "image_model_id" in changes or "image_dtype" in changes:
        try:
            from app.services.image_generator import configure_image_generator
            configure_image_generator(
                model_id=get("image_model_id"),
                dtype_name=get("image_dtype"),
            )
            _log.info(
                "[settings] Image generator reconfigured: model=%s dtype=%s",
                get("image_model_id"), get("image_dtype"),
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

    # ── Persist user preferences to ~/.aicss/settings.json ───────────────────
    # Only changes that are NOT marked "sensitive" go to disk; this avoids
    # saving API keys by accident. Sensitive fields stay in process env only.
    persistable = {
        k: v for k, v in changes.items()
        if k not in SENSITIVE_FIELDS and v is not None
    }
    if persistable:
        try:
            from app.services.settings_store import save_overrides
            save_overrides(persistable)
        except Exception as exc:
            _log.warning("[settings] could not persist overrides: %s", exc)

    return get_settings()
