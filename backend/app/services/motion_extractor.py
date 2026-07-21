"""
Motion Extractor Service
Generates action videos and extracts character motion as PNG sequences.

Video generation is delegated to VideoProvider backends via video_adapter:
  - "dashscope"  — DashScope wan2.7-i2v (cloud, high quality)
  - "local_wan"  — wan2.1-i2v local inference (28GB+ VRAM)
  - "svd"        — Stable Video Diffusion (8GB VRAM, degraded quality)

Configure via settings.video_provider or pass provider="svd" to generate_action_video().
"""
from __future__ import annotations

import base64
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


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
) -> Optional[str]:
    """
    Generate action video via the configured VideoProvider.

    Args:
        prompt: Action description text
        start_image_b64: Optional first frame (base64)
        end_image_b64: Optional last frame (base64)
        duration_seconds: Target video length in seconds
        provider: One of "dashscope", "local_wan", "svd"

    Returns:
        Local path to the generated video file, or None on failure.
    """
    try:
        from .video_adapter import get_video_provider
        video_provider = get_video_provider(provider)
        return await video_provider.generate(prompt, start_image_b64, end_image_b64, duration_seconds)
    except Exception as e:
        logger.warning("[motion_extractor] generate_action_video failed: %s", e)
        return None


# ── Frame Extraction ─────────────────────────────────────────────────────────────

def extract_frames_from_video(
    video_path: str,
    output_dir: str,
    fps: float = 30.0,
    max_frames: int = 300,
) -> list[str]:
    """
    Extract PNG frames from video using ffmpeg.
    Returns list of frame file paths.
    """
    import subprocess

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    for f in output_dir_path.glob("frame_*.png"):
        f.unlink()

    try:
        cmd = [
            "ffmpeg", "-i", video_path,
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
            logger.warning("[motion_extractor] ffmpeg failed: %s", result.stderr)
            return []

        frames = sorted(str(f) for f in output_dir_path.glob("frame_*.png"))
        logger.info("[motion_extractor] Extracted %d frames from %s", len(frames), video_path)
        return frames

    except FileNotFoundError:
        logger.warning("[motion_extractor] ffmpeg not found — install ffmpeg for frame extraction")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("[motion_extractor] Frame extraction timed out")
        return []
    except Exception as e:
        logger.warning("[motion_extractor] Frame extraction error: %s", e)
        return []


# ── SAM2 Segmentation ───────────────────────────────────────────────────────────

def segment_person_from_frame(
    frame_path: str,
    output_path: str,
    sam2_model,
    min_area: int = 1000,
) -> bool:
    """
    Segment person from a single frame using SAM2.
    Saves RGBA PNG with transparent background.
    Returns True if successful.
    """
    try:
        import cv2

        image = cv2.imread(frame_path)
        if image is None:
            return False

        masks = sam2_model.predict_automatic_masks(image)
        if not masks:
            return False

        person_mask = None
        for mask_data in masks:
            seg = mask_data.get("segmentation") or mask_data.get("mask")
            if seg is None:
                continue
            area = float(seg.sum())
            if area > min_area and person_mask is None:
                person_mask = (seg.astype(np.uint8) * 255)

        if person_mask is None:
            return False

        h, w = person_mask.shape[:2]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        bgr = image[:, :, :3]
        rgba[:, :, :3] = bgr
        rgba[:, :, 3] = person_mask

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

        success = segment_person_from_frame(frame_path, str(out_file), sam2_model, min_area)
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
    output_base_dir: str = "backend/.cache/motion",
    sam2_model=None,
    video_provider: str = "dashscope",
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
    """
    motion = MotionSequence(
        shot_id=shot_id,
        character_id=character_id,
        character_name=character_name,
        action_description=action_prompt,
        status="generating",
    )

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
    )

    if not video_path:
        motion.status = "error"
        motion.error = f"Video generation failed (provider={video_provider})"
        return motion

    motion.video_path = video_path
    motion.status = "extracting"

    # 2. Extract frames
    motion.frame_dir = str(shot_dir / "frames")
    frames = extract_frames_from_video(video_path, motion.frame_dir)
    if not frames:
        motion.status = "error"
        motion.error = "Frame extraction failed (ffmpeg error)"
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
