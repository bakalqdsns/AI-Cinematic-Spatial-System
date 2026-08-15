"""
Motion Extractor Service
Generates action videos and extracts character motion as PNG sequences.

Video generation is delegated to VideoProvider backends via video_adapter:
  - "dashscope"   — DashScope VideoSynthesis API (wan2.5-i2v-preview, cloud, high quality, paid)
  - "happyhorse"  — DashScope happyhorse-1.1-r2v (cloud, lower quality, ~10 free trial calls)
  - "local_wan"   — wan2.1-i2v local inference (28GB+ VRAM)
  - "svd"         — Stable Video Diffusion (8GB VRAM, degraded quality)

Both "dashscope" and "happyhorse" share the same DashScope API key
(`dashscope_video_api_key`). Each provider's underlying model name is hard-coded
in `app/services/video_adapter.py`.

Configure via settings.video_provider or pass provider="happyhorse" to
generate_action_video().
"""
from __future__ import annotations

import base64
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import CACHE_DIR

logger = logging.getLogger(__name__)


# ── Chroma key constants ──────────────────────────────────────────────────────────

GREEN_KEY_BGR = (0, 255, 0)
GREENSCREEN_PROMPT_SUFFIX = (
    ", solid bright green (#00FF00) chroma key background, "
    "no other objects in background, flat lighting"
)


# ── Dataclasses ─────────────────────────────────────────────────────────────────

@dataclass
class MotionSequence:
    shot_id: str
    character_id: str
    character_name: str
    action_description: str
    video_path: Optional[str] = None
    video_url: Optional[str] = None
    frame_count: int = 0
    frame_dir: Optional[str] = None
    segmented_dir: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None


@dataclass
class SegmentedFrame:
    frame_index: int
    original_path: str
    segmented_path: str
    character_name: str
    action_name: str


# ── Video Generation ─────────────────────────────────────────────────────────────

async def generate_action_video(
    prompt: str,
    start_image_b64: Optional[str] = None,
    end_image_b64: Optional[str] = None,
    duration_seconds: float = 5.0,
    provider: str = "dashscope",
    greenscreen: bool = False,
) -> Optional[str]:
    """
    Generate action video via the configured VideoProvider.

    Args:
        prompt: Action description text
        start_image_b64: Optional first frame (base64)
        end_image_b64: Optional last frame (base64)
        duration_seconds: Target video length in seconds
        provider: One of "dashscope", "local_wan", "svd"
        greenscreen: When True, prepend a chroma-key background directive to
            the provider prompt so the generated video features a flat green
            backdrop. The matching post-processing pass happens in
            :func:`segment_person_from_frame`.

    Returns:
        Local path to the generated video file, or None on failure.
    """
    try:
        from .video_adapter import get_video_provider
        video_provider = get_video_provider(provider)
        return await video_provider.generate(
            prompt,
            start_image_b64,
            end_image_b64,
            duration_seconds,
            greenscreen=greenscreen,
        )
    except Exception as e:
        logger.warning("[motion_extractor] generate_action_video failed: %s", e)
        return None


# ── Frame Extraction ─────────────────────────────────────────────────────────────

def extract_frames_from_video(
    video_path: str,
    output_dir: str,
    fps: float = 30.0,
    max_frames: int = 300,
    ffmpeg_path: Optional[str] = None,
) -> list[str]:
    """
    Extract PNG frames from video using ffmpeg.

    Args:
        video_path: Source video file.
        output_dir: Directory to write frame_*.png files into.
        fps: Sampling rate.
        max_frames: Hard cap on number of frames extracted.
        ffmpeg_path: Optional explicit path to ffmpeg binary. When None the
            function falls back to ``shutil.which("ffmpeg")`` and raises
            RuntimeError if ffmpeg is not on PATH.

    Returns:
        Sorted list of frame file paths.

    Raises:
        RuntimeError: If ffmpeg is not on PATH or fails on the video.
    """
    import os
    import subprocess

    explicit = ffmpeg_path or os.environ.get("FFMPEG_PATH")
    resolved_ffmpeg = explicit if explicit and Path(explicit).exists() else shutil.which("ffmpeg")
    if resolved_ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found in PATH. Install ffmpeg (https://ffmpeg.org/) "
            "or set the FFMPEG_PATH environment variable (must point to an "
            "existing file) or pass ffmpeg_path=... before starting the "
            "backend. Frame extraction is required for the motion pipeline."
        )

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    for f in output_dir_path.glob("frame_*.png"):
        f.unlink()

    try:
        cmd = [
            resolved_ffmpeg, "-i", video_path,
            "-vf", f"fps={fps},scale=1024:1024",
            "-frames:v", str(max_frames),
            "-q:v", "2",
            str(output_dir_path / "frame_%04d.png"),
            "-y",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[-500:]
            raise RuntimeError(
                f"ffmpeg failed (returncode={result.returncode}) on "
                f"{video_path}: {stderr}"
            )

        frames = sorted(str(f) for f in output_dir_path.glob("frame_*.png"))
        logger.info("[motion_extractor] Extracted %d frames from %s", len(frames), video_path)
        return frames

    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Frame extraction timed out after 300s for {video_path}") from e
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Frame extraction error for {video_path}: {e}") from e


# ── SAM2 Segmentation ───────────────────────────────────────────────────────────

def chroma_key_rgba(
    rgba_bgr: np.ndarray,
    key_color: tuple[int, int, int] = GREEN_KEY_BGR,
    threshold: int = 80,
    softness: int = 20,
) -> np.ndarray:
    """
    Apply a soft chroma key over an RGBA image (BGR channel order).

    Pixels whose Euclidean distance to ``key_color`` is below ``threshold``
    get alpha=0; pixels farther than ``threshold + softness`` keep alpha=255;
    pixels in between ramp linearly. The result is an RGBA image where the
    green-screen background is fully transparent and the edge feathers
    smoothly over ``softness`` units of distance.

    Args:
        rgba_bgr: HxWx4 uint8 array in BGR channel order.
        key_color: BGR triplet to remove (default pure green).
        threshold: Distance below which alpha becomes 0.
        softness: Distance band over which alpha ramps from 0 to 255.

    Returns:
        New HxWx4 uint8 RGBA array with rewritten alpha channel.
    """
    b = rgba_bgr[:, :, 0].astype(np.int32)
    g = rgba_bgr[:, :, 1].astype(np.int32)
    r = rgba_bgr[:, :, 2].astype(np.int32)

    diff = np.sqrt(
        (b - key_color[0]) ** 2
        + (g - key_color[1]) ** 2
        + (r - key_color[2]) ** 2
    )

    if softness <= 0:
        new_alpha = np.where(diff >= threshold, 255, 0).astype(np.uint8)
    else:
        ramp = np.clip(((diff - threshold) * 255.0) / softness, 0.0, 255.0)
        new_alpha = ramp.astype(np.uint8)

    out = rgba_bgr.copy()
    out[:, :, 3] = new_alpha
    return out


def segment_person_from_frame(
    frame_path: str,
    output_path: str,
    sam2_model,
    min_area: int = 1000,
    feather_edges: bool = True,
    greenscreen: bool = False,
    chroma_threshold: int = 80,
    chroma_softness: int = 20,
    snap_distance: int = 8,
) -> bool:
    """
    Segment person from a single frame using SAM2.

    Saves an RGBA PNG with transparent background. When ``feather_edges`` is
    True (default) the SAM2 mask is snapped to nearby Canny edges via
    :func:`app.models.sam2_loader.refine_mask_edges` to soften the silhouette.
    When ``greenscreen`` is True an additional chroma-key pass is applied on
    top of the SAM2 alpha (green-screen pixels become fully transparent).

    Args:
        frame_path: Input PNG frame from ffmpeg.
        output_path: Destination RGBA PNG.
        sam2_model: Pre-loaded SAM2 model instance.
        min_area: Discard masks smaller than this pixel area.
        feather_edges: Whether to call refine_mask_edges on the SAM2 output.
        greenscreen: Whether to apply an additional chroma-key pass.
        chroma_threshold: Chroma key distance threshold (see chroma_key_rgba).
        chroma_softness: Chroma key feather band.
        snap_distance: Max pixel distance for Canny-edge snapping.

    Returns:
        True if segmentation succeeded and the file was written.
    """
    try:
        import cv2

        image = cv2.imread(frame_path)
        if image is None:
            return False

        masks = sam2_model.predict_automatic_masks(image)
        if masks is None:
            return False
        # Real SAM2 returns numpy arrays; guard against bool ambiguity
        try:
            if len(masks) == 0:
                return False
        except TypeError:
            return False

        person_mask = None
        for mask_data in masks:
            seg = mask_data.get("segmentation")
            if seg is None:
                seg = mask_data.get("mask")
            if seg is None:
                continue
            area = float(seg.sum())
            if area > min_area and person_mask is None:
                person_mask = (seg.astype(np.uint8) * 255)

        if person_mask is None:
            return False

        if feather_edges:
            try:
                from app.models.sam2_loader import refine_mask_edges
                image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                refined = refine_mask_edges(
                    [(person_mask.astype(bool), 1.0)],
                    image_rgb,
                    snap_distance=snap_distance,
                )
                if refined:
                    person_mask = (refined[0][0].astype(np.uint8) * 255)
            except Exception as e:
                logger.warning(
                    "[motion_extractor] refine_mask_edges failed, "
                    "falling back to raw SAM2 mask: %s",
                    e,
                )

        h, w = person_mask.shape[:2]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        bgr = image[:, :, :3]
        rgba[:, :, :3] = bgr
        rgba[:, :, 3] = person_mask

        if greenscreen:
            rgba = chroma_key_rgba(
                rgba,
                key_color=GREEN_KEY_BGR,
                threshold=chroma_threshold,
                softness=chroma_softness,
            )

        cv2.imwrite(output_path, rgba)
        return True

    except Exception as e:
        logger.warning("[motion_extractor] SAM2 segmentation error on %s: %s", frame_path, e)
        return False


def segment_frames_sequence(
    frame_paths: list[str],
    output_dir: str,
    sam2_model,
    character_name: str,
    action_name: str,
    min_area: int = 1000,
    feather_edges: bool = True,
    greenscreen: bool = False,
    chroma_threshold: int = 80,
    chroma_softness: int = 20,
    snap_distance: int = 8,
) -> list[SegmentedFrame]:
    """
    Segment person from a sequence of frames.
    Names output as: {characterName}_{actionName}_{frameIndex:04d}.png
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    segmented = []
    for i, frame_path in enumerate(frame_paths):
        safe_char = character_name.replace(" ", "_")
        safe_action = action_name.replace(" ", "_")
        out_file = output_path / f"{safe_char}_{safe_action}_{i:04d}.png"

        success = segment_person_from_frame(
            frame_path,
            str(out_file),
            sam2_model,
            min_area=min_area,
            feather_edges=feather_edges,
            greenscreen=greenscreen,
            chroma_threshold=chroma_threshold,
            chroma_softness=chroma_softness,
            snap_distance=snap_distance,
        )
        segmented.append(SegmentedFrame(
            frame_index=i,
            original_path=frame_path,
            segmented_path=str(out_file) if success else "",
            character_name=character_name,
            action_name=action_name,
        ))

    return segmented


# ── Full Pipeline ───────────────────────────────────────────────────────────────

async def generate_motion_sequence(
    shot_id: str,
    character_id: str,
    character_name: str,
    action_prompt: str,
    start_image_b64: Optional[str] = None,
    end_image_b64: Optional[str] = None,
    duration_seconds: float = 5.0,
    output_base_dir: str = None,
    sam2_model=None,
    video_provider: str = "dashscope",
    greenscreen: bool = False,
    feather_edges: bool = True,
    chroma_threshold: int = 80,
    chroma_softness: int = 20,
    snap_distance: int = 8,
) -> MotionSequence:
    """
    Full pipeline: generate video -> extract frames -> segment -> RGBA PNG output.

    Args:
        shot_id, character_id, character_name, action_prompt: Identifiers and description.
        start_image_b64 / end_image_b64: Optional keyframes (base64).
        duration_seconds: Target video length.
        output_base_dir: Root directory for cached outputs.
        sam2_model: Pre-loaded SAM2 model instance (None = auto-detect from model_manager).
        video_provider: Video provider name ("dashscope", "local_wan", "svd").
        greenscreen: Forward a green-screen background directive to the video
            provider and apply a chroma-key pass during segmentation.
        feather_edges: Snap SAM2 masks to nearby Canny edges for softer silhouettes.
        chroma_threshold: Lower bound for the chroma key distance (greenscreen mode).
        chroma_softness: Feather band over which alpha ramps from 0 to 255.
        snap_distance: Max pixel distance for Canny-edge snapping (feather mode).
    """
    motion = MotionSequence(
        shot_id=shot_id,
        character_id=character_id,
        character_name=character_name,
        action_description=action_prompt,
        status="generating",
    )

    if output_base_dir is None:
        output_base_dir = str(CACHE_DIR / "motion")

    safe_char = character_name.replace(" ", "_")
    safe_action = action_prompt[:30].replace(" ", "_").replace("/", "_")
    shot_dir = Path(output_base_dir) / f"{safe_char}_{safe_action}"
    shot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate video
    video_path = await generate_action_video(
        prompt=action_prompt,
        start_image_b64=start_image_b64,
        end_image_b64=end_image_b64,
        duration_seconds=duration_seconds,
        provider=video_provider,
        greenscreen=greenscreen,
    )

    if not video_path:
        motion.status = "error"
        motion.error = f"Video generation failed (provider={video_provider})"
        return motion

    motion.video_path = video_path
    motion.status = "extracting"

    # 2. Extract frames (raises RuntimeError on ffmpeg absence / failure)
    motion.frame_dir = str(shot_dir / "frames")
    try:
        frames = extract_frames_from_video(video_path, motion.frame_dir)
    except RuntimeError as e:
        motion.status = "error"
        motion.error = str(e)
        return motion

    if not frames:
        motion.status = "error"
        motion.error = "Frame extraction returned no frames"
        return motion

    motion.frame_count = len(frames)
    motion.status = "segmenting"
    motion.segmented_dir = str(shot_dir / "segmented")

    # 3. Segment
    if sam2_model is None:
        try:
            from app.models import model_manager
            if model_manager.is_loaded():
                sam2_model = model_manager.sam2
        except Exception:
            pass

    if sam2_model:
        segment_frames_sequence(
            frames,
            motion.segmented_dir,
            sam2_model,
            character_name,
            safe_action,
            feather_edges=feather_edges,
            greenscreen=greenscreen,
            chroma_threshold=chroma_threshold,
            chroma_softness=chroma_softness,
            snap_distance=snap_distance,
        )
        motion.status = "done"
    else:
        motion.status = "error"
        motion.error = "SAM2 model not available"

    return motion


def serialize_motion_sequence(motion: MotionSequence) -> dict:
    return {
        "shot_id": motion.shot_id,
        "character_id": motion.character_id,
        "character_name": motion.character_name,
        "action_description": motion.action_description,
        "video_path": motion.video_path,
        "video_url": motion.video_url,
        "frame_count": motion.frame_count,
        "frame_dir": motion.frame_dir,
        "segmented_dir": motion.segmented_dir,
        "status": motion.status,
        "error": motion.error,
    }
