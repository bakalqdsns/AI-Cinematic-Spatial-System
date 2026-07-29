"""
Auto Three-View Generator
=========================

When /parse completes, the user wants every detected character to
automatically get its front/side/back reference set generated — no manual
click per character. This module owns:

  * a process-wide in-memory status table (project_id → per-character state)
  * the batch worker that runs after /parse finishes (fire-and-forget)
  * a wrapper around the shared GPU semaphore so character + scene workers
    don't collectively OOM the GPU
  * the public helpers used by endpoints and stores

Status table shape:
    {
      project_id: {
        char_id: {
          "name": str,
          "status": "queued" | "running" | "done" | "failed",
          "started_at": float,
          "finished_at": Optional[float],
          "error": Optional[str],
          "visual_prompt": Optional[str],
          "asset": Optional[dict],   # serialised CharacterAsset
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .character_generator import (
    CharacterAsset,
    build_character_asset,
    generate_character_three_view,
    generate_visual_prompt,
    serialize_character_asset,
)
from .script_parser import Character, ScriptLanguage
from ..utils.gpu_concurrency import get_gpu_sem

logger = logging.getLogger(__name__)


# ── Process-wide state ──────────────────────────────────────────────────────────

# Per-project → per-character progress map.
_PROGRESS: dict[str, dict[str, dict]] = {}
_PROGRESS_LOCK = asyncio.Lock()

# GPU concurrency is shared across every background worker (characters,
# scenes, …). See app.utils.gpu_concurrency for the limit + reasoning.


def get_progress(project_id: str) -> dict[str, dict]:
    """Read-only snapshot of the per-project progress table."""
    proj = _PROGRESS.get(project_id, {})
    return {k: dict(v) for k, v in proj.items()}


def clear_progress(project_id: str) -> None:
    """Drop the progress table for a project (call when the project is deleted)."""
    _PROGRESS.pop(project_id, None)


# ── Worker ──────────────────────────────────────────────────────────────────────

async def auto_generate_three_views_for_project(
    *,
    project_id: str,
    characters: list[Character],
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> None:
    """
    Fire-and-forget batch worker.

    Schedules every character for three-view generation, bounded by
    ``_MAX_CONCURRENT_CHARACTERS``. Each character's progress (queued /
    running / done / failed) is written to ``_PROGRESS[project_id]``.

    Returns nothing; callers should ``asyncio.create_task(...)`` this.
    """
    if not characters:
        return

    # Initialise per-character state to "queued".
    async with _PROGRESS_LOCK:
        proj = _PROGRESS.setdefault(project_id, {})
        for c in characters:
            proj[c.id] = {
                "name": c.name,
                "status": "queued",
                "started_at": 0.0,
                "finished_at": None,
                "error": None,
                "visual_prompt": None,
                "asset": None,
            }

    # Lazy import to avoid a circular dependency at module load.
    from app.services import project_store

    sem = get_gpu_sem()

    async def _one(char: Character) -> None:
        async with sem:
            # Mark as running.
            async with _PROGRESS_LOCK:
                _PROGRESS[project_id][char.id].update({
                    "status": "running",
                    "started_at": time.time(),
                })

            try:
                logger.info(
                    "[auto_3view] %s start character=%s", project_id, char.name,
                )

                # ── 1. resolve visual prompt (LLM) ─────────────────────────────
                visual_prompt = char.visual_prompt
                if not visual_prompt:
                    visual_prompt = await generate_visual_prompt(char, genre=genre, language=language)

                # ── 2. generate three views (SDXL anchor + 2x img2img) ───────
                three_view = await generate_character_three_view(
                    char, visual_prompt=visual_prompt,
                )

                # ── 3. detect silent failures ────────────────────────────────
                # When every view is None the generation provider (DashScope or
                # local) failed silently. Surface this as a failed entry instead
                # of "done" so the UI can show an error badge.
                failed_views = [k for k, v in three_view.items() if not v]
                if failed_views:
                    raise RuntimeError(
                        f"Image generation returned no data for {failed_views} views. "
                        f"Check: (1) DashScope API key is set, (2) wanx-v1 quota "
                        f"is not exhausted, (3) network connectivity to "
                        f"dashscope.aliyuncs.com."
                    )

                # ── 4. build asset ───────────────────────────────────────────
                ref_b64 = three_view.get("front")
                asset = build_character_asset(char, ref_b64, three_view)
                asset.visual_prompt = visual_prompt
                serialised = serialize_character_asset(asset)

                # ── 5. persist to project store ──────────────────────────────
                try:
                    await project_store.save_character_asset(
                        project_id, char.id, payload=serialised,
                        character_name=char.name or char.id,
                        action_name="three_view",
                        frame_index=0,
                    )
                except Exception as e:
                    logger.warning(
                        "[auto_3view] %s save failed for %s: %s",
                        project_id, char.name, e,
                    )

                async with _PROGRESS_LOCK:
                    _PROGRESS[project_id][char.id].update({
                        "status": "done",
                        "finished_at": time.time(),
                        "visual_prompt": visual_prompt,
                        "asset": serialised,
                    })
                logger.info(
                    "[auto_3view] %s done character=%s", project_id, char.name,
                )

            except Exception as e:
                logger.exception("[auto_3view] %s failed for %s", project_id, char.name)
                async with _PROGRESS_LOCK:
                    _PROGRESS[project_id][char.id].update({
                        "status": "failed",
                        "finished_at": time.time(),
                        "error": str(e),
                    })

    # Fan out all characters concurrently (semaphore inside `_one` caps real
    # GPU usage to ``_MAX_CONCURRENT_CHARACTERS``).
    await asyncio.gather(*[_one(c) for c in characters], return_exceptions=True)

    logger.info("[auto_3view] %s all characters finished", project_id)


# ── Convenience wrapper used by endpoints ───────────────────────────────────────

async def kickoff_after_parse(
    *,
    project_id: str,
    characters: list[Character],
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> Optional[asyncio.Task]:
    """
    Spawn the auto-batch as a background task. Returns the Task so callers
    can (optionally) attach a done-callback, or ``None`` when there's
    nothing to do.
    """
    if not project_id or not characters:
        return None
    return asyncio.create_task(
        auto_generate_three_views_for_project(
            project_id=project_id,
            characters=characters,
            genre=genre,
            language=language,
        )
    )
