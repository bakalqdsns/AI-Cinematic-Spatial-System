"""
Persistent user-settings storage.

User overrides to runtime settings (cloud provider choice, model IDs, custom
provider registry, ...) are persisted to ``~/.aicss/settings.json`` so the
preferences survive process restarts.

This module is intentionally a thin wrapper around a JSON file:
  - ``load_overrides()`` — read user-set values at startup
  - ``save_overrides(patch)`` — write user-set values after each update
  - ``apply_overrides()`` — convenience: load + apply to ``config.settings``

Sensitive fields (API keys) are stored as-is. The file is written with mode
0600 on POSIX so only the owner can read it; on Windows the underlying
filesystem ACLs apply. Callers that need additional protection should layer
OS-level encryption on top.

Failure mode: if the file is missing / corrupt / unreadable, the loader
silently returns an empty dict — defaults from ``config.py`` stay in effect.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SETTINGS_DIR = Path(os.environ.get("AICSS_SETTINGS_DIR", str(Path.home() / ".aicss")))
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
_VERSION = 1

_lock = threading.Lock()


def _ensure_dir() -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def _read_file() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("[settings-store] settings.json is not a dict — ignoring")
            return {}
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[settings-store] could not read %s: %s", SETTINGS_FILE, e)
        return {}


def _atomic_write(payload: dict) -> None:
    """Write atomically via tmp + replace to avoid leaving a half-written file."""
    _ensure_dir()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(SETTINGS_DIR), prefix=".settings-", suffix=".json.tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SETTINGS_FILE)
        # On POSIX, tighten permissions (no-op on Windows)
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except OSError:
            pass
    except Exception:
        # Best-effort cleanup of the tmp file
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def load_overrides() -> dict:
    """
    Read user overrides from disk.

    Returns an empty dict on any failure (missing file, parse error, permission).
    The shape mirrors what callers push via `update_settings` — only keys that
    the user has explicitly overridden should be present.
    """
    with _lock:
        raw = _read_file()
    overrides = raw.get("overrides", {}) if isinstance(raw, dict) else {}
    if not isinstance(overrides, dict):
        return {}
    return overrides


def save_overrides(patch: dict) -> None:
    """
    Merge `patch` into the persisted overrides file.

    The on-disk structure is:
        {
            "version": 1,
            "overrides": {<key>: <value>, ...}
        }

    Existing entries that aren't in `patch` are preserved. To clear a value,
    set it to `None` (Pydantic-friendly "no override" sentinel).
    """
    if not isinstance(patch, dict):
        return
    with _lock:
        current = _read_file()
        existing_overrides = current.get("overrides", {}) if isinstance(current, dict) else {}
        if not isinstance(existing_overrides, dict):
            existing_overrides = {}
        # Merge: patch wins; None entries delete the override
        merged = {**existing_overrides}
        for k, v in patch.items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
        payload = {"version": _VERSION, "overrides": merged}
        _atomic_write(payload)
        logger.info(
            "[settings-store] persisted %d override(s) to %s",
            len(merged), SETTINGS_FILE,
        )


def apply_overrides() -> int:
    """
    Load overrides from disk and apply them to the live runtime values store.

    Returns the number of overrides applied. Used at app startup. Writes go
    through ``settings_manager.seed_overrides()`` so consumers reading via
    ``settings_manager.get()`` see the persisted values without
    ``config.settings`` being mutated.
    """
    from app.services.settings_manager import seed_overrides
    overrides = load_overrides()
    if not overrides:
        logger.info("[settings-store] no overrides found on disk")
        return 0
    applied = seed_overrides(overrides)
    if applied:
        logger.info(
            "[settings-store] applied %d override(s) from %s",
            applied, SETTINGS_FILE,
        )
    return applied


def settings_file_path() -> str:
    """Return the absolute path of the persisted settings file (for the UI)."""
    return str(SETTINGS_FILE)