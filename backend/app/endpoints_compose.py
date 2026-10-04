"""
Compose API Endpoints
REST endpoints for FFmpeg-backed video composition (Module 11).

Provides:
  POST /api/aicss/v2/projects/{project_id}/compose 鈥?Compose clips into a
                                                    single MP4 with optional
                                                    transitions / audio / grade.
  POST /api/aicss/v2/projects/{project_id}/render-queue 鈥?Batch-render
                                                    multiple shots via Blender
                                                    headless (T07).

Reference: docs/EXECUTION_TASKS.md (T01 / T02 / T04 / T05 / T07)
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.video_composer import compose_clips

logger = logging.getLogger("aicss")

router = APIRouter(prefix="/api/aicss/v2", tags=["compose"])


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Request / Response Models
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class AudioTrack(BaseModel):
    """A single audio track layered onto the final video."""
    kind: Literal["bgm", "sfx", "voiceover"] = Field(
        ..., description="bgm loops to video length; sfx/voiceover are delayed to start_at.",
    )
    path: str = Field(..., description="Absolute path to the audio file (mp3/wav/aac).")
    volume: float = Field(
        1.0, ge=0.0, le=2.0,
        description="Volume multiplier applied to this track (1.0 = unity).",
    )
    start_at: float = Field(
        0.0, ge=0.0,
        description="Seconds offset into the final timeline where this track begins.",
    )


class ColorGrade(BaseModel):
    """Optional color grade applied as the final composition step."""
    lut_path: Optional[str] = Field(
        None, description="Path to a .cube LUT file. When set, lut3d is applied first.",
    )
    brightness: float = Field(0.0, ge=-1.0, le=1.0, description="eq brightness.")
    contrast: float = Field(1.0, ge=0.0, le=10.0, description="eq contrast (1.0 = unity).")
    saturation: float = Field(1.0, ge=0.0, le=3.0, description="eq saturation (1.0 = unity).")


class ComposeRequest(BaseModel):
    """Request body for POST /projects/{project_id}/compose."""
    clipPaths: list[str] = Field(
        ..., min_length=1, description="Ordered list of source MP4 clip paths.",
    )
    durations: list[float] = Field(
        default_factory=list,
        description="Per-clip target durations (seconds). Informational; used for "
                    "transition clamping. When empty, durations are probed from the clips.",
    )
    transition: Literal["cut", "dissolve", "fade", "wipe"] = Field(
        "cut", description="Transition kind applied between adjacent clips.",
    )
    transitionDuration: float = Field(
        0.5, ge=0.0, le=5.0, description="Transition duration in seconds.",
    )
    audioTracks: Optional[list[AudioTrack]] = Field(
        None, description="Optional audio tracks mixed onto the final video (T04).",
    )
    colorGrade: Optional[ColorGrade] = Field(
        None, description="Optional color grade applied as the last step (T05).",
    )


class ComposeResponse(BaseModel):
    """Response for POST /projects/{project_id}/compose."""
    outputPath: str = Field(..., description="Absolute path to the composed MP4.")
    durationSeconds: float = Field(..., description="Total duration of the output in seconds.")
    format: str = Field("mp4", description="Output container format.")


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Endpoint
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.post("/projects/{project_id}/compose", response_model=ComposeResponse)
async def api_compose(project_id: str, request: ComposeRequest) -> ComposeResponse:
    """
    Compose a list of shot MP4 clips into a single 1080p H.264 MP4.

    Pipeline (all async, ffmpeg via ``asyncio.create_subprocess_exec``):
      1. Normalise every clip to 1080p yuv420p H.264.
      2. Pairwise apply transitions (cut / dissolve / fade / wipe).
      3. (Optional) mix audio tracks (BGM / SFX / voiceover) with loudnorm.
      4. (Optional) apply color grade (.cube LUT or eq brightness/contrast/saturation).

    Error mapping:
      - ``FFMPEG_MISSING`` 鈫?503
      - Any other ``RuntimeError`` from the composer 鈫?500
    """
    try:
        output_path = await compose_clips(
            clip_paths=request.clipPaths,
            durations=request.durations,
            transition=request.transition,
            transition_duration=request.transitionDuration,
            project_id=project_id,
            audio_tracks=[t.model_dump() for t in request.audioTracks] if request.audioTracks else None,
            color_grade=request.colorGrade.model_dump() if request.colorGrade else None,
        )
    except RuntimeError as exc:
        msg = str(exc)
        # Surface the first token as the machine-readable error code.
        code = msg.split(":", 1)[0].strip()
        if code == "FFMPEG_MISSING":
            raise HTTPException(status_code=503, detail="FFMPEG_MISSING")
        logger.warning("[compose] failed: %s", msg)
        raise HTTPException(status_code=500, detail=msg[:500])
    except Exception as exc:
        logger.exception("[compose] unexpected error")
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}"[:500])

    # Probe final duration for the response.
    duration = 0.0
    try:
        from app.services.video_composer import _probe_duration
        duration = await _probe_duration(output_path)
    except Exception as exc:
        logger.warning("[compose] failed to probe final duration: %s", exc)

    return ComposeResponse(
        outputPath=output_path,
        durationSeconds=duration,
        format="mp4",
    )


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Stream composed MP4 鈥?browser-playable endpoint
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@router.get(
    "/projects/{project_id}/compose/{filename}",
    response_class=FileResponse,
    summary="Stream a composed MP4",
)
async def get_composed_video(project_id: str, filename: str):
    """Return the composed MP4 file for browser playback.

    The compose step writes to ``workspace/projects/<pid>/compose/<filename>``.
    This endpoint streams it back with the correct MIME type so the frontend
    ``<video>`` tag can play it.
    """
    # 瀹夊叏锛歠ilename 涓嶅厑璁稿惈璺緞鍒嗛殧绗︽垨 ..
    if os.path.sep in filename or "/" in filename or ".." in filename:
        raise HTTPException(404, "Not found")
    # 瀹氫綅鏂囦欢
    from app.config import settings
    compose_dir = settings.workspace_dir / "projects" / project_id / "compose"
    path = compose_dir / filename
    if not path.is_file():
        raise HTTPException(404, "Composed video not found")
    return FileResponse(
        str(path),
        media_type="video/mp4",
        filename=filename,
    )


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# T07 鈥?Render Queue (Blender headless batch render)
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class RenderQueueResult(BaseModel):
    """Per-shot render outcome."""
    shotId: str = Field(..., description="Shot ID as known to the project.")
    status: Literal["succeeded", "failed"] = Field(
        ..., description="succeeded = MP4 written; failed = error recorded.",
    )
    outputPath: Optional[str] = Field(
        None, description="Absolute path to the rendered MP4 (when succeeded).",
    )
    error: Optional[str] = Field(
        None, description="Error message (when failed).",
    )


class RenderQueueRequest(BaseModel):
    """Request body for POST /projects/{project_id}/render-queue."""
    shotIds: list[str] = Field(
        ..., min_length=1, description="Shot IDs to render. Each must have a "
        "packed archive at projects/<pid>/archives/<pid>_<shot_id>_archive.zip.",
    )
    samples: int = Field(
        32, ge=1, le=4096, description="Cycles sample count.",
    )
    resolution: tuple[int, int] = Field(
        (1920, 1080), description="(width, height) in pixels.",
    )
    device: Literal["GPU", "CPU"] = Field(
        "GPU", description="Cycles device. Falls back to CPU if GPU unavailable.",
    )
    fps: int = Field(24, ge=1, le=120, description="Timeline frame rate.")
    lightingPreset: Optional[str] = Field(
        None, description="Override manifest's lightingPreset. Empty = read "
        "from manifest, fallback warm_interior.",
    )


class RenderQueueResponse(BaseModel):
    """Response for POST /projects/{project_id}/render-queue."""
    results: list[RenderQueueResult] = Field(
        default_factory=list, description="Per-shot outcomes, in request order.",
    )
    totalSucceeded: int = Field(0, ge=0)
    totalFailed: int = Field(0, ge=0)
    blenderAvailable: bool = Field(
        ..., description="False when Blender executable not found; results will be empty.",
    )


def _find_blender_executable() -> Optional[str]:
    """Reuse mesh_exporter's Blender lookup so the render-queue endpoint and
    the mesh exporter share the same discovery logic."""
    try:
        from app.services.mesh_exporter import _find_blender
        return _find_blender()
    except Exception:
        return None


def _addon_dir() -> Path:
    """Absolute path to the aicss_scene_builder addon source."""
    backend_root = Path(__file__).resolve().parents[1]
    return backend_root / "blender" / "addons" / "aicss_scene_builder"


def _resolve_shot_manifest(project_id: str, shot_id: str, staging: Path) -> Optional[str]:
    """Unzip the shot archive into ``staging/<shot_id>/`` and return the
    absolute path to its ``manifest.json``. Returns None when the archive
    is missing or the manifest is absent."""
    from app.services.project_store import WORKSPACE_DIR
    project_dir = WORKSPACE_DIR / project_id
    candidates = [
        project_dir / "archives" / f"{project_id}_{shot_id}_archive.zip",
        # Allow already-unpacked manifests as a fallback (e.g. dev workflows)
        project_dir / "shots" / shot_id / "manifest.json",
    ]
    print(f"[render-queue] resolve project_id={project_id!r} shot_id={shot_id!r} project_dir={project_dir!r}", flush=True)
    for cand in candidates:
        print(f"[render-queue] candidate={cand!r} exists={cand.exists()}", flush=True)
        if not cand.exists():
            continue
        if cand.suffix == ".zip":
            target = staging / shot_id
            target.mkdir(parents=True, exist_ok=True)
            try:
                import zipfile
                with zipfile.ZipFile(cand, "r") as zf:
                    zf.extractall(target)
            except Exception as exc:
                logger.warning("[render-queue] failed to unzip %s: %s", cand, exc)
                return None
            manifest = target / "manifest.json"
            return str(manifest) if manifest.is_file() else None
        # Already a manifest file
        return str(cand)
    return None


def _run_render_queue_blender(
    project_id: str,
    manifest_paths: list[str],
    output_dir: str,
    *,
    samples: int,
    resolution: tuple[int, int],
    device: str,
    fps: int,
    lighting_preset: Optional[str],
    timeout_seconds: int = 1800,
) -> dict:
    """Invoke Blender headless to run the ``aicss.render_queue`` operator.

    Returns the parsed ``render_queue_results.json`` dict (or an error
    envelope when Blender itself is missing / times out).
    """
    blender_path = _find_blender_executable()
    if not blender_path:
        return {
            "results": [],
            "totalSucceeded": 0,
            "totalFailed": 0,
            "blenderAvailable": False,
            "error": "Blender executable not found. Set BLENDER_EXECUTABLE or install Blender.",
        }

    addon_path = _addon_dir()
    # Blender script: register the addon, run the operator, exit.
    manifest_arg = ";".join(manifest_paths)
    preset_arg = lighting_preset or ""
    res_x, res_y = resolution

    blender_script = f'''
import sys
import os
import json
import bpy

# Make the addon importable without installing it.
sys.path.insert(0, r"{addon_path.parent}")
import aicss_scene_builder
aicss_scene_builder.register()

manifest_paths = r"{manifest_arg}".split(";")
output_dir = r"{output_dir}"
samples = {samples}
res_x = {res_x}
res_y = {res_y}
device = "{device}"
fps = {fps}
preset = r"{preset_arg}"

try:
    bpy.ops.aicss.render_queue(
        manifest_paths=";".join(manifest_paths),
        output_dir=output_dir,
        project_id=r"{project_id}",
        samples=samples,
        resolution_x=res_x,
        resolution_y=res_y,
        device=device,
        fps=fps,
        lighting_preset=preset,
        continue_on_error=True,
    )
except Exception as exc:
    print("[render-queue] operator raised:", exc)

# The operator writes render_queue_results.json next to the renders.
results_path = os.path.join(output_dir, "render_queue_results.json")
try:
    with open(results_path, "r", encoding="utf-8") as fp:
        print("===RENDER_QUEUE_RESULTS_BEGIN===")
        print(fp.read())
        print("===RENDER_QUEUE_RESULTS_END===")
except Exception as exc:
    print("[render-queue] failed to read results:", exc)
'''

    with tempfile.TemporaryDirectory(prefix="aicss_render_queue_") as tmp:
        script_path = Path(tmp) / "render_queue.py"
        script_path.write_text(blender_script, encoding="utf-8")
        print(f"[render-queue] launching Blender: {blender_path}", flush=True)
        print(f"[render-queue] manifest_paths: {manifest_paths}", flush=True)
        print(f"[render-queue] output_dir: {output_dir}", flush=True)

        try:
            result = subprocess.run(
                [blender_path, "--background", "--python", str(script_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {
                "results": [],
                "totalSucceeded": 0,
                "totalFailed": len(manifest_paths),
                "blenderAvailable": True,
                "error": f"Blender render timed out after {timeout_seconds}s",
            }
        except FileNotFoundError:
            return {
                "results": [],
                "totalSucceeded": 0,
                "totalFailed": 0,
                "blenderAvailable": False,
                "error": f"Blender executable not found at: {blender_path}",
            }

        # Parse the marker-delimited JSON from stdout
        stdout = result.stdout or ""
        begin = stdout.find("===RENDER_QUEUE_RESULTS_BEGIN===")
        end = stdout.find("===RENDER_QUEUE_RESULTS_END===")
        if begin != -1 and end != -1 and end > begin:
            payload = stdout[begin + len("===RENDER_QUEUE_RESULTS_BEGIN==="):end].strip()
            try:
                parsed = json.loads(payload)
                parsed.setdefault("blenderAvailable", True)
                logger.warning("[render-queue] parsed results: %s", json.dumps(parsed, ensure_ascii=False)[:1000])
                return parsed
            except Exception as exc:
                logger.warning("[render-queue] failed to parse results JSON: %s", exc)

        # Fallback: try reading the file directly
        results_file = Path(output_dir) / "render_queue_results.json"
        if results_file.is_file():
            try:
                parsed = json.loads(results_file.read_text(encoding="utf-8"))
                parsed.setdefault("blenderAvailable", True)
                logger.warning("[render-queue] file results: %s", json.dumps(parsed, ensure_ascii=False)[:1000])
                return parsed
            except Exception:
                pass

        logger.warning(
            "[render-queue] Blender exit=%d, no results JSON. stderr tail: %s",
            result.returncode, (result.stderr or "")[-500:],
        )
        logger.warning("[render-queue] Blender stdout:\n%s", (result.stdout or "")[-3000:])
        logger.warning("[render-queue] Blender stderr:\n%s", (result.stderr or "")[-3000:])
        return {
            "results": [],
            "totalSucceeded": 0,
            "totalFailed": len(manifest_paths),
            "blenderAvailable": True,
            "error": f"Blender exit {result.returncode}; no results JSON. stderr: {(result.stderr or '')[-300:]}",
        }


@router.post(
    "/projects/{project_id}/render-queue",
    response_model=RenderQueueResponse,
)
async def api_render_queue(project_id: str, request: RenderQueueRequest) -> RenderQueueResponse:
    """
    Batch-render multiple shots via Blender headless.

    For each ``shotId`` the endpoint:
      1. Unzips ``projects/<pid>/archives/<pid>_<shot_id>_archive.zip`` to a
         temp dir.
      2. Invokes Blender headless with the AICSS addon registered.
      3. The addon's ``aicss.render_queue`` operator imports layers, sets
         camera animation, adds lighting, and renders each shot to
         ``projects/<pid>/renders/<shot_id>.mp4``.
      4. Per-shot status is collected from ``render_queue_results.json``.

    Error mapping:
      - Blender not found 鈫?200 with ``blenderAvailable=false`` (so the
        caller can surface a soft warning instead of a 500).
      - Shot archive missing 鈫?that shot is reported as ``failed`` with an
        error message; the rest of the queue continues.
    """
    from app.services.project_store import WORKSPACE_DIR
    project_dir = WORKSPACE_DIR / project_id
    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    renders_dir = project_dir / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aicss_render_staging_") as tmp:
        staging = Path(tmp)
        manifest_paths: list[str] = []
        missing: list[RenderQueueResult] = []
        for shot_id in request.shotIds:
            mp = _resolve_shot_manifest(project_id, shot_id, staging)
            if mp is None:
                missing.append(RenderQueueResult(
                    shotId=shot_id, status="failed",
                    error=f"Shot archive not found for {shot_id} in {project_id}",
                ))
            else:
                manifest_paths.append(mp)

        if not manifest_paths and not missing:
            # Nothing to do
            return RenderQueueResponse(
                results=[], totalSucceeded=0, totalFailed=0,
                blenderAvailable=True,
            )

        if manifest_paths:
            summary = _run_render_queue_blender(
                project_id=project_id,
                manifest_paths=manifest_paths,
                output_dir=str(renders_dir),
                samples=request.samples,
                resolution=request.resolution,
                device=request.device,
                fps=request.fps,
                lighting_preset=request.lightingPreset,
            )
        else:
            summary = {
                "results": [], "totalSucceeded": 0, "totalFailed": 0,
                "blenderAvailable": True,
            }

        blender_available = bool(summary.get("blenderAvailable", True))
        # Merge operator results with the missing-shot list
        op_results = []
        for r in summary.get("results", []):
            try:
                op_results.append(RenderQueueResult(
                    shotId=str(r.get("shotId", "")),
                    status=r.get("status", "failed"),
                    outputPath=r.get("outputPath"),
                    error=r.get("error"),
                ))
            except Exception:
                continue

        all_results = op_results + missing
        succeeded = sum(1 for r in all_results if r.status == "succeeded")
        failed = sum(1 for r in all_results if r.status == "failed")

        if not blender_available:
            # Surface a 503 so callers can distinguish "Blender missing"
            # from "some shots failed".
            raise HTTPException(
                status_code=503,
                detail=summary.get("error", "BLENDER_MISSING"),
            )

        return RenderQueueResponse(
            results=all_results,
            totalSucceeded=succeeded,
            totalFailed=failed,
            blenderAvailable=blender_available,
        )


