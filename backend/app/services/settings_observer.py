"""
Settings Observer — event bus for runtime settings changes.

Phase 1 architecture deliverable (Implementation Plan §1.4.1). Adds an
observer pattern on top of `settings_manager.update_settings()` so that
consumers (LLM, ImageGen, CloudRouter, ...) are notified via callbacks
instead of having to poll `config.settings` for changes.

This decouples consumers from the global singleton by giving them a
typed callback (`on_setting_changed`) rather than implicit reads of
`config.settings`. Existing `setattr(settings, key, value)` calls inside
`update_settings()` are kept (backward compatibility) but the observer
pattern lets new code register explicit handlers.

Usage:
    from app.services.settings_observer import (
        SettingsObserver, register_observer, notify_setting_change,
    )

    class MyObserver(SettingsObserver):
        def on_setting_changed(self, key: str, value, old_value) -> None:
            if key == "image_model_id":
                reconfigure_image_generator(value)

    register_observer("image_gen", MyObserver())
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class SettingsObserver(Protocol):
    """Observer interface for settings change notifications.

    The default implementation in this module is a no-op base class, so
    subclasses can override only the methods they care about (Python's
    duck typing means callers can also pass any object with the same
    method signature).
    """

    def on_setting_changed(self, key: str, value: Any, old_value: Any) -> None:
        """Called when a single setting changes.

        Args:
            key: The setting name (e.g. "image_model_id").
            value: The new value.
            old_value: The previous value (None if this is the first time).
        """
        ...


class _NoopObserver:
    """Default observer — does nothing. Useful as a sentinel."""

    def on_setting_changed(self, key: str, value, old_value) -> None:
        return None


# ── Observer registry ───────────────────────────────────────────────────────────

_observers: dict[str, SettingsObserver] = {}
_observers_lock = threading.RLock()


def register_observer(name: str, observer: SettingsObserver) -> None:
    """Register an observer under a unique name.

    Re-registering with the same name replaces the previous observer.
    Names should be descriptive (e.g. "image_gen", "llm", "cloud_router").
    """
    if not isinstance(observer, SettingsObserver):
        # Use the runtime checkable protocol — works for any object with
        # the right method signature, not just our base class.
        if not hasattr(observer, "on_setting_changed"):
            raise TypeError(
                f"Observer must implement on_setting_changed(); got {type(observer)}"
            )
    with _observers_lock:
        _observers[name] = observer
    logger.info("[settings-observer] registered %s", name)


def unregister_observer(name: str) -> None:
    """Remove a previously-registered observer. Safe to call if not present."""
    with _observers_lock:
        _observers.pop(name, None)
    logger.info("[settings-observer] unregistered %s", name)


def list_observers() -> list[str]:
    """Return the names of all registered observers (for diagnostics)."""
    with _observers_lock:
        return sorted(_observers.keys())


def notify_setting_change(key: str, value: Any, old_value: Any = None) -> None:
    """Fan out a single setting change to every registered observer.

    Errors in one observer don't propagate to others — the loop catches
    and logs each exception so a buggy consumer can't break the whole
    notification chain.
    """
    with _observers_lock:
        observers_snapshot = list(_observers.items())
    for name, obs in observers_snapshot:
        try:
            obs.on_setting_changed(key, value, old_value)
        except Exception as exc:
            logger.warning(
                "[settings-observer] %s.on_setting_changed(%s) raised: %s",
                name, key, exc,
            )


def notify_bulk(changes: dict[str, Any], previous: Optional[dict[str, Any]] = None) -> None:
    """Notify observers of multiple setting changes at once.

    Each key in ``changes`` is sent individually to every observer, with
    the previous value looked up in ``previous`` (or reported as None
    when not present). Used by ``settings_manager.update_settings`` so
    consumers see a coherent view of all changes.
    """
    previous = previous or {}
    for key, value in changes.items():
        old = previous.get(key)
        notify_setting_change(key, value, old)


# ── Convenience: subscribe via plain function ─────────────────────────────────

def register_callback(
    name: str,
    callback: Callable[[str, Any, Any], None],
    key_filter: Optional[Callable[[str], bool]] = None,
) -> None:
    """Register a plain function as an observer.

    Useful for one-off consumers that don't want to declare a full class.
    The optional ``key_filter`` lets the callback ignore keys it doesn't
    care about (avoiding the overhead of being called for every change).
    """

    class _FnObserver:
        def on_setting_changed(self, key, value, old_value):
            if key_filter is None or key_filter(key):
                callback(key, value, old_value)

    register_observer(name, _FnObserver())


# ── Built-in observers (optional convenience) ─────────────────────────────────


class ImageGeneratorObserver:
    """Reconfigures the image generator when its settings change.

    Demonstrates the observer pattern: instead of polling
    ``config.settings.image_model_id`` on every generation, we react to
    explicit change events. Use via::

        from app.services.settings_observer import register_observer
        register_observer("image_gen", ImageGeneratorObserver())
    """

    TRIGGER_KEYS = ("image_model_id", "image_dtype")

    def on_setting_changed(self, key: str, value, old_value) -> None:
        if key not in self.TRIGGER_KEYS or value == old_value:
            return
        try:
            from app.services.image_generator import configure_image_generator
            configure_image_generator(
                model_id=value if key == "image_model_id" else _current_or("image_model_id"),
                dtype_name=value if key == "image_dtype" else _current_or("image_dtype"),
            )
            logger.info("[image-gen-observer] reconfigured due to %s change", key)
        except Exception as exc:
            logger.warning("[image-gen-observer] reconfigure failed: %s", exc)


class LLMObserver:
    """Reconfigures the LLM client when its settings change."""

    TRIGGER_KEYS = ("llm_base_url", "llm_model", "model_mode")

    def on_setting_changed(self, key: str, value, old_value) -> None:
        if key not in self.TRIGGER_KEYS or value == old_value:
            return
        try:
            if key in ("llm_base_url", "llm_model"):
                from app.services.local_llm import configure_llm
                configure_llm(
                    base_url=_current_or("llm_base_url"),
                    model=_current_or("llm_model"),
                    timeout=_current_or("llm_timeout"),
                )
            elif key == "model_mode":
                from app.services.local_llm import set_use_cloud
                set_use_cloud(value == "cloud")
            logger.info("[llm-observer] applied %s change", key)
        except Exception as exc:
            logger.warning("[llm-observer] reconfigure failed: %s", exc)


class ModelModeCascadeObserver:
    """
    Cascades ``model_mode`` changes to ``vlm_mode`` / ``image_mode`` /
    ``video_mode`` so the user doesn't have to set each sub-mode manually.

    Only cascades when the corresponding sub-mode is currently a *default*
    value (i.e. hasn't been explicitly set by the user). This avoids
    overwriting intentional per-component overrides.

    Registered automatically by ``app.main`` at startup so the cascade is
    active as soon as the settings observer is up.
    """

    DEFAULT_VALUES = {"cloud", "local"}

    def on_setting_changed(self, key: str, value, old_value) -> None:
        if key != "model_mode" or value == old_value:
            return
        if value not in ("cloud", "local"):
            return
        try:
            from app.services.settings_manager import get as _get, set_runtime_value
            cascaded: list[str] = []
            for sub_key in ("vlm_mode", "image_mode", "video_mode"):
                current = _get(sub_key, None)
                if current in self.DEFAULT_VALUES:
                    set_runtime_value(sub_key, value)
                    cascaded.append(f"{sub_key}={value}")
            if cascaded:
                logger.info(
                    "[model-mode-cascade] cascaded model_mode=%s to %s",
                    value, ", ".join(cascaded),
                )
                # Persist the cascaded values so the next restart sees them
                try:
                    from app.services.settings_store import save_overrides
                    save_overrides({k.split("=")[0]: value for k in cascaded})
                except Exception as exc:
                    logger.warning("[model-mode-cascade] persist failed: %s", exc)
                # Wake up any subscribers that listen for these sub-mode keys
                try:
                    from app.services.settings_observer import notify_setting_change
                    for k in cascaded:
                        sub_key, sub_val = k.split("=", 1)
                        notify_setting_change(sub_key, sub_val, None)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("[model-mode-cascade] failed: %s", exc)


def _current_or(key: str, default=None):
    """Read the current value of a setting without crashing on import errors."""
    try:
        from app.services.settings_manager import get as _get
        return _get(key, default)
    except Exception:
        return default