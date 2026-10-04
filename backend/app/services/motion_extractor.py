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
class KeyframeConsistencyResult:
    """Result of comparing a generated video frame against the input keyframe."""
    passed: bool
    ncc_score: float          # Normalized Cross-Correlation, 0-1 (higher = more similar)
    mse_score: float          # Mean Squared Error, 0-1 normalised (lower = more similar)
    orb_inliers: Optional[int]  # ORB inlier count if computed, else None
    method: str               # Which method triggered the final decision
    details: str               # Human-readable one-line summary

    def summary(self) -> str:
        return self.details


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
    first_frame_consistency: Optional[KeyframeConsistencyResult] = None
    last_frame_consistency: Optional[KeyframeConsistencyResult] = None


@dataclass
class SegmentedFrame:
    frame_index: int
    original_path: str
    segmented_path: str
    character_name: str
    action_name: str


# ── Keyframe Consistency Check ─────────────────────────────────────────────────

import cv2

# Thresholds — tune per visual fidelity requirement.
# NCC: higher = more similar (TM_CCOEFF_NORMED output range ≈ [-1, 1] normalised)
NCC_THRESHOLD      = 0.70   # Pass if ≥ 0.70 (pixel-level correlation)
# MSE: lower = more similar; normalised to [0,1] where 0 = identical
MSE_THRESHOLD      = 0.30   # Pass if ≤ 0.30 after normalisation to uint8 space
# ORB: inlier ratio; higher = structural alignment
ORB_INLIER_MIN     = 15     # Require ≥ 15 ORB inliers for structural pass


def verify_keyframe_consistency(
    generated_frame_path: str,
    reference_keyframe_b64: str,
    *,
    ncc_threshold: float = NCC_THRESHOLD,
    mse_threshold: float = MSE_THRESHOLD,
    orb_inlier_min: int = ORB_INLIER_MIN,
) -> KeyframeConsistencyResult:
    """
    Compare ``generated_frame_path`` (first or last extracted frame) against
    ``reference_keyframe_b64`` (the base64 image the caller originally passed to
    the video generation API).

    Uses a three-tier strategy:

    1. **NCC (fast)** — Normalized Cross-Correlation. Fast but sensitive to
       colour shifts and brightness differences. If NCC ≥ ``ncc_threshold``
       the check passes immediately.

    2. **MSE (medium)** — Resize both images to a common tiny resolution
       (64×64) to dampen aliasing, then compute normalised MSE on grayscale.
       Fast and quantifies pixel-level distortion.

    3. **ORB (slow / structural)** — Only invoked if NCC < ncc_threshold.
       Detects ORB features in both images, matches them, and counts inliers
       after geometric verification. Most robust against lighting/colour
       changes. ``orb_inlier_min`` inliers are required to pass.

    Returns ``KeyframeConsistencyResult(passed, ncc_score, mse_score,
    orb_inliers, method, details)``.
    """
    import io
    from PIL import Image

    # Decode reference keyframe
    try:
        data64 = reference_keyframe_b64
        if data64.startswith("data:"):
            data64 = data64.split(",", 1)[1]
        raw = base64.b64decode(data64)
        ref_img = Image.open(io.BytesIO(raw)).convert("RGB")
        ref_np  = np.array(ref_img)
        ref_gray = cv2.cvtColor(ref_np, cv2.COLOR_RGB2GRAY)
    except Exception as exc:
        return KeyframeConsistencyResult(
            passed=False,
            ncc_score=0.0,
            mse_score=1.0,
            orb_inliers=None,
            method="decode",
            details=f"Failed to decode reference keyframe: {exc}",
        )

    # Load generated frame
    try:
        gen_bgr  = cv2.imread(generated_frame_path)
        if gen_bgr is None:
            raise IOError(f"cv2.imread returned None for {generated_frame_path!r}")
        gen_rgb  = cv2.cvtColor(gen_bgr, cv2.COLOR_BGR2RGB)
        gen_gray = cv2.cvtColor(gen_rgb, cv2.COLOR_RGB2GRAY)
    except Exception as exc:
        return KeyframeConsistencyResult(
            passed=False,
            ncc_score=0.0,
            mse_score=1.0,
            orb_inliers=None,
            method="decode",
            details=f"Failed to read generated frame: {exc}",
        )

    # Resize reference to match generated frame dimensions
    gh, gw = gen_gray.shape
    ref_resized = cv2.resize(ref_gray, (gw, gh), interpolation=cv2.INTER_AREA)

    # ── Tier 1: NCC ───────────────────────────────────────────────────────────
    ncc_score = cv2.matchTemplate(
        ref_resized.astype(np.float32),
        gen_gray.astype(np.float32),
        cv2.TM_CCOEFF_NORMED,
    )[0, 0]
    ncc_score = float(np.clip(ncc_score, -1.0, 1.0))

    if ncc_score >= ncc_threshold:
        details = (
            f"NCC={ncc_score:.3f} ≥ {ncc_threshold} — pixel-level correlation OK "
            f"(resolution {gw}×{gh})"
        )
        return KeyframeConsistencyResult(
            passed=True,
            ncc_score=ncc_score,
            mse_score=1.0,       # not computed
            orb_inliers=None,
            method="ncc",
            details=details,
        )

    # ── Tier 2: MSE ────────────────────────────────────────────────────────────
    small_ref = cv2.resize(ref_resized, (64, 64), interpolation=cv2.INTER_AREA)
    small_gen = cv2.resize(gen_gray,     (64, 64), interpolation=cv2.INTER_AREA)
    mse_raw   = float(np.mean((small_ref.astype(np.float32) - small_gen.astype(np.float32)) ** 2))
    # Normalise MSE to [0,1] using theoretical max (255² ≈ 65025)
    mse_score = min(1.0, mse_raw / 65025.0)

    if mse_score <= mse_threshold:
        details = (
            f"NCC={ncc_score:.3f} < {ncc_threshold}, MSE={mse_score:.3f} ≤ "
            f"{mse_threshold} after 64×64 — overall similarity acceptable"
        )
        return KeyframeConsistencyResult(
            passed=True,
            ncc_score=ncc_score,
            mse_score=mse_score,
            orb_inliers=None,
            method="mse",
            details=details,
        )

    # ── Tier 3: ORB structural matching ────────────────────────────────────────
    orb_detector = cv2.ORB_create(nfeatures=500)
    kp1, des1 = orb_detector.detectAndCompute(small_ref, None)
    kp2, des2 = orb_detector.detectAndCompute(small_gen, None)

    if des1 is None or des2 is None or len(des1) < 3 or len(des2) < 3:
        details = (
            f"NCC={ncc_score:.3f}, MSE={mse_score:.3f}, ORB insufficient features "
            f"({len(des1 or [])}, {len(des2 or [])}) — cannot verify structurally"
        )
        return KeyframeConsistencyResult(
            passed=False,
            ncc_score=ncc_score,
            mse_score=mse_score,
            orb_inliers=None,
            method="orb_insufficient",
            details=details,
        )

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(des1, des2)

    # Geometric verification: keep matches consistent with a similarity transform
    inliers = 0
    for m in matches:
        dx = kp2[m.trainIdx].pt[0] - kp1[m.queryIdx].pt[0]
        dy = kp2[m.trainIdx].pt[1] - kp1[m.queryIdx].pt[1]
        # Allow up to 25% of the small image size for positional drift
        max_drift = max(small_ref.shape[1], small_ref.shape[0]) * 0.25
        if abs(dx) <= max_drift and abs(dy) <= max_drift:
            inliers += 1

    orb_inliers = inliers
    passed = orb_inliers >= orb_inlier_min

    details = (
        f"NCC={ncc_score:.3f}, MSE={mse_score:.3f}, ORB inliers={orb_inliers} "
        f"({'PASS' if passed else f'< {orb_inlier_min}'}) — "
        f"{'structural match' if passed else 'significant deviation from keyframe'}"
    )
    return KeyframeConsistencyResult(
        passed=passed,
        ncc_score=ncc_score,
        mse_score=mse_score,
        orb_inliers=orb_inliers,
        method="orb",
        details=details,
    )


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
        RuntimeError: If ffmpeg cannot be located (after checking
            ffmpeg_path, FFMPEG_PATH, imageio-ffmpeg's bundled binary,
            and the system PATH) or fails on the video.
    """
    import os
    import subprocess

    explicit = ffmpeg_path or os.environ.get("FFMPEG_PATH")
    if explicit and Path(explicit).exists():
        resolved_ffmpeg = explicit
    else:
        try:
            import imageio_ffmpeg

            resolved_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            resolved_ffmpeg = shutil.which("ffmpeg")

    if resolved_ffmpeg is None:
        raise RuntimeError(
            "ffmpeg not found. Resolution order: (1) ffmpeg_path kwarg, "
            "(2) FFMPEG_PATH env var pointing to an existing binary, "
            "(3) imageio-ffmpeg bundled binary, (4) system PATH. "
            "Install via `pip install imageio-ffmpeg` for the bundled "
            "option, or `winget install ffmpeg` / `choco install ffmpeg` "
            "for a system-wide install."
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

    # ── 2b. Keyframe consistency check ─────────────────────────────────────────
    # Compare the generated video's first / last extracted frames against the
    # original keyframes the caller passed in.  Results are written directly to
    # motion.first_frame_consistency / motion.last_frame_consistency so callers
    # can surface a warning without blocking the pipeline.
    if start_image_b64 and len(frames) > 0:
        motion.first_frame_consistency = verify_keyframe_consistency(
            frames[0], start_image_b64
        )
        logger.info(
            "[motion] first-frame consistency: %s",
            motion.first_frame_consistency.details,
        )
        if not motion.first_frame_consistency.passed:
            motion.error = (
                f"First-frame mismatch (NCC={motion.first_frame_consistency.ncc_score:.3f}, "
                f"MSE={motion.first_frame_consistency.mse_score:.3f}, "
                f"method={motion.first_frame_consistency.method}). "
                "Video may not respect the start keyframe."
            )
            logger.warning("[motion] %s", motion.error)

    if end_image_b64 and len(frames) > 1:
        motion.last_frame_consistency = verify_keyframe_consistency(
            frames[-1], end_image_b64
        )
        logger.info(
            "[motion] last-frame consistency: %s",
            motion.last_frame_consistency.details,
        )
        if not motion.last_frame_consistency.passed:
            motion.error = (
                f"Last-frame mismatch (NCC={motion.last_frame_consistency.ncc_score:.3f}, "
                f"MSE={motion.last_frame_consistency.mse_score:.3f}, "
                f"method={motion.last_frame_consistency.method}). "
                "Video may not respect the end keyframe."
            )

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


def _consistency_dict(c: Optional[KeyframeConsistencyResult]) -> Optional[dict]:
    if c is None:
        return None
    return {
        "passed": c.passed,
        "ncc_score": c.ncc_score,
        "mse_score": c.mse_score,
        "orb_inliers": c.orb_inliers,
        "method": c.method,
        "details": c.details,
    }


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
        "first_frame_consistency": _consistency_dict(motion.first_frame_consistency),
        "last_frame_consistency": _consistency_dict(motion.last_frame_consistency),
    }
