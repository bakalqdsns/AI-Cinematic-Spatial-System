"""
Motion Extractor Service
Generates action videos and extracts character motion as PNG sequences.
"""
import base64
import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


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
    status: str = "pending"  # pending, generating, extracting, segmenting, done, error
    error: Optional[str] = None


@dataclass
class SegmentedFrame:
    frame_index: int
    original_path: str
    segmented_path: str
    character_name: str
    action_name: str


# --- Video Generation ---

async def generate_action_video(
    prompt: str,
    start_image_b64: Optional[str] = None,
    end_image_b64: Optional[str] = None,
    duration_seconds: float = 5.0,
    provider: str = "dashscope",
) -> Optional[str]:
    """
    Generate action video from prompt + optional start/end keyframes.
    Uses DashScope Wan 2.7-i2v for image-to-video generation.
    Returns path to downloaded video file.
    """
    if provider == "dashscope":
        return await _generate_video_dashscope(prompt, start_image_b64, end_image_b64, duration_seconds)
    else:
        logger.warning(f"Video provider {provider} not implemented")
        return None


async def _generate_video_dashscope(
    prompt: str,
    start_image_b64: Optional[str],
    end_image_b64: Optional[str],
    duration_seconds: float,
) -> Optional[str]:
    """Generate video via DashScope Wan 2.7-i2v async task API."""
    try:
        import dashscope
        from dashscope.api.entities.dashscope import FilmConcurrentRequest

        request = FilmConcurrentRequest(
            model="wan2.7-i2v",
            prompt=prompt,
        )

        # Add first clip from start image if provided
        if start_image_b64:
            request.add_clip_first_frame(
                image=start_image_b64,
                duration=duration_seconds,
            )

        # Add last frame if end image is provided
        if end_image_b64:
            request.add_clip_last_frame(
                image=end_image_b64,
                duration=1.0,
            )

        task_response = dashscope.Film.call(
            request=request,
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        )

        if task_response.status != 200:
            logger.warning(f"DashScope video task creation failed: {task_response.message}")
            return None

        task_id = task_response.output.task_id
        logger.info(f"Video generation task created: {task_id}")

        # Poll for completion (up to 5 minutes)
        import time
        max_wait = 300
        elapsed = 0
        while elapsed < max_wait:
            status_resp = dashscope.Film.fetch(task_id=task_id)
            status = status_resp.output.task_status
            if status == "succeed":
                video_url = status_resp.output.video.video_url
                return await _download_video(video_url)
            elif status in ("failed", "error"):
                logger.warning(f"Video generation failed: {status_resp.output}")
                return None
            time.sleep(10)
            elapsed += 10

        logger.warning(f"Video generation timed out after {max_wait}s")
        return None

    except Exception as e:
        logger.warning(f"DashScope video generation error: {e}")
        return None


async def _download_video(url: str) -> Optional[str]:
    """Download video from URL to temp directory."""
    try:
        import httpx
        from dashscope.common.constant import DEFAULT_API_ENDPOINTS

        # Use the direct URL from task response
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            # Save to temp directory
            cache_dir = Path("backend/.cache/videos")
            cache_dir.mkdir(parents=True, exist_ok=True)
            video_path = cache_dir / f"{uuid.uuid4().hex[:8]}.mp4"

            with open(video_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

            return str(video_path)
    except Exception as e:
        logger.warning(f"Failed to download video: {e}")
        return None


# --- Frame Extraction ---

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
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    # Clean existing frames
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
            logger.warning(f"ffmpeg failed: {result.stderr}")
            return []

        frames = sorted(str(f) for f in output_dir_path.glob("frame_*.png"))
        logger.info(f"Extracted {len(frames)} frames from {video_path}")
        return frames

    except FileNotFoundError:
        logger.warning("ffmpeg not found. Install ffmpeg for frame extraction.")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("Frame extraction timed out")
        return []
    except Exception as e:
        logger.warning(f"Frame extraction error: {e}")
        return []


# --- SAM2 Segmentation ---

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
        from PIL import Image
        import numpy as np

        # Read image
        image = cv2.imread(frame_path)
        if image is None:
            return False

        # Run SAM2 automatic segmentation
        masks = sam2_model.predict_automatic_masks(image)
        if not masks:
            return False

        # Find person mask (highest scoring person-class mask)
        person_mask = None
        for mask_data in masks:
            # Try to detect person using GroundingDINO or just use largest mask
            # For simplicity, use the largest mask that looks like a person
            mask = mask_data.get("segmentation")
            if mask is None:
                mask = mask_data.get("mask")
            if mask is None:
                continue

            area = mask.sum()
            if area > min_area and person_mask is None:
                person_mask = mask.astype(np.uint8) * 255

        if person_mask is None:
            return False

        # Apply mask to create RGBA image
        h, w = person_mask.shape[:2]
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        bgr = image[:, :, :3]
        rgba[:, :, :3] = bgr
        rgba[:, :, 3] = person_mask

        # Save
        cv2.imwrite(output_path, rgba)
        return True

    except Exception as e:
        logger.warning(f"SAM2 segmentation error on {frame_path}: {e}")
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
    Returns list of SegmentedFrame objects.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    segmented = []
    for i, frame_path in enumerate(frame_paths):
        safe_char = character_name.replace(" ", "_")
        safe_action = action_name.replace(" ", "_")
        output_file = output_path / f"{safe_char}_{safe_action}_{i:04d}.png"

        success = segment_person_from_frame(
            frame_path,
            str(output_file),
            sam2_model,
            min_area,
        )

        segmented.append(SegmentedFrame(
            frame_index=i,
            original_path=frame_path,
            segmented_path=str(output_file) if success else "",
            character_name=character_name,
            action_name=action_name,
        ))

    return segmented


# --- Full Pipeline ---

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
) -> MotionSequence:
    """
    Full pipeline: generate video -> extract frames -> segment -> named PNG output.
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

    video_path = await generate_action_video(
        prompt=action_prompt,
        start_image_b64=start_image_b64,
        end_image_b64=end_image_b64,
        duration_seconds=duration_seconds,
    )

    if not video_path:
        motion.status = "error"
        motion.error = "Video generation failed"
        return motion

    motion.video_path = video_path
    motion.status = "extracting"
    motion.frame_dir = str(shot_dir / "frames")

    frames = extract_frames_from_video(video_path, motion.frame_dir)
    if not frames:
        motion.status = "error"
        motion.error = "Frame extraction failed"
        return motion

    motion.frame_count = len(frames)
    motion.status = "segmenting"
    motion.segmented_dir = str(shot_dir / "segmented")

    if sam2_model is None:
        # Try to get from model manager
        try:
            from ..models import model_manager
            if model_manager.is_loaded():
                sam2_model = model_manager.sam2
        except Exception:
            pass

    if sam2_model:
        segmented = segment_frames_sequence(
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