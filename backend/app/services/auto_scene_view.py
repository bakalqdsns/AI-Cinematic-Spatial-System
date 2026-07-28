"""
Auto Scene Keyframe Generator
=============================

Fires immediately after /parse: every detected scene gets its wide / closeup /
mood keyframes generated automatically in the background (no per-scene click).

Progress is exposed via ``get_progress(project_id)`` so the frontend can poll
``/scenes/batch-status`` and ingest finished assets as they arrive.

GPU concurrency is shared with the character three-view worker via
``app.utils.gpu_concurrency`` — see that module for the cap.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from .scene_generator import (
    SceneAsset,
    build_scene_asset,
    generate_scene_keyframes,
    generate_scene_visual_prompt,
    serialize_scene_asset,
)
from .script_parser import Scene, ScriptLanguage
from ..utils.gpu_concurrency import get_gpu_sem

logger = logging.getLogger(__name__)


# ── Process-wide state ──────────────────────────────────────────────────────────

_PROGRESS: dict[str, dict[str, dict]] = {}
_PROGRESS_LOCK = asyncio.Lock()


def get_progress(project_id: str) -> dict[str, dict]:
    proj = _PROGRESS.get(project_id, {})
    return {k: dict(v) for k, v in proj.items()}


def clear_progress(project_id: str) -> None:
    _PROGRESS.pop(project_id, None)


# ── Worker ──────────────────────────────────────────────────────────────────────

async def auto_generate_scene_assets_for_project(
    *,
    project_id: str,
    scenes: list[Scene],
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> None:
    """Fire-and-forget batch worker. Awaited only by tests."""
    if not scenes:
        return

    async with _PROGRESS_LOCK:
        proj = _PROGRESS.setdefault(project_id, {})
        for s in scenes:
            proj[s.id] = {
                "name": s.location or s.id,
                "status": "queued",
                "started_at": 0.0,
                "finished_at": None,
                "error": None,
                "visual_prompt": None,
                "asset": None,
            }

    from app.services import project_store

    sem = get_gpu_sem()

    async def _one(scene: Scene) -> None:
        async with sem:
            async with _PROGRESS_LOCK:
                _PROGRESS[project_id][scene.id].update({
                    "status": "running",
                    "started_at": time.time(),
                })

            try:
                logger.info("[auto_scene] %s start scene=%s", project_id, scene.location)

                visual_prompt = scene.visual_prompt
                if not visual_prompt:
                    visual_prompt = await generate_scene_visual_prompt(
                        scene, genre=genre, language=language,
                    )

                keyframes = await generate_scene_keyframes(
                    scene, visual_prompt=visual_prompt,
                )

                asset = build_scene_asset(scene, keyframes)
                asset.visual_prompt = visual_prompt
                serialised = serialize_scene_asset(asset)

                try:
                    await project_store.save_scene_asset(
                        project_id, scene.id, payload=serialised,
                    )
                except Exception as e:
                    logger.warning(
                        "[auto_scene] %s save failed for %s: %s",
                        project_id, scene.location, e,
                    )

                async with _PROGRESS_LOCK:
                    _PROGRESS[project_id][scene.id].update({
                        "status": "done",
                        "finished_at": time.time(),
                        "visual_prompt": visual_prompt,
                        "asset": serialised,
                    })
                logger.info("[auto_scene] %s done scene=%s", project_id, scene.location)

            except Exception as e:
                logger.exception("[auto_scene] %s failed for %s", project_id, scene.location)
                async with _PROGRESS_LOCK:
                    _PROGRESS[project_id][scene.id].update({
                        "status": "failed",
                        "finished_at": time.time(),
                        "error": str(e),
                    })

    await asyncio.gather(*[_one(s) for s in scenes], return_exceptions=True)
    logger.info("[auto_scene] %s all scenes finished", project_id)


async def kickoff_after_parse(
    *,
    project_id: str,
    scenes: list[Scene],
    genre: str = "cinematic",
    language: ScriptLanguage = ScriptLanguage.CHINESE,
) -> Optional[asyncio.Task]:
    if not project_id or not scenes:
        return None
    return asyncio.create_task(
        auto_generate_scene_assets_for_project(
            project_id=project_id,
            scenes=scenes,
            genre=genre,
            language=language,
        )
    )