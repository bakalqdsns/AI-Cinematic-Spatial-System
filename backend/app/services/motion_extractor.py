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
from app.services.project_store import slugify

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
            :func:`generate_motion_sequence` (chroma key, then SAM2 when loaded).

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
            "-vf",
            # Keep aspect ratio: fit inside 1024x1024 instead of stretching to a
            # square, and round to even dimensions for codec compatibility.
            f"fps={fps},scale=1024:1024:force_original_aspect_ratio=decrease:force_divisible_by=2",
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

def _border_band_thickness(height: int, width: int) -> int:
    """Width of the frame-edge strip used to read the screen color."""
    return max(2, min(height, width) // 32)


def _bgr_distance(pixels: np.ndarray, key_color: tuple[int, int, int]) -> np.ndarray:
    """Euclidean BGR distance from ``pixels`` (..., 3) to ``key_color``."""
    delta = pixels.astype(np.int32) - np.asarray(key_color, dtype=np.int32)
    return np.sqrt(np.sum(delta * delta, axis=-1))


def _looks_like_greenscreen_bgr(color: tuple[int, int, int] | np.ndarray) -> bool:
    """True when a sampled border color is a green plate, including off-pure plates.

    Generated footage often drifts off ``#00FF00`` toward a flat light green
    (the paper-cut plate is about BGR 134, 179, 116). That still has a green
    hue and a clearly leading green channel. Gray, skin, red, and yellow do not.
    """
    b = int(round(float(color[0])))
    g = int(round(float(color[1])))
    r = int(round(float(color[2])))
    if g < 100 or g - max(r, b) < 24:
        return False
    pixel = np.uint8([[[b, g, r]]])
    hue = int(cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0, 0])
    return 40 <= hue <= 100


def _sample_edge_screen_bgr(
    bgr: np.ndarray,
    key_color: tuple[int, int, int],
    threshold: int,
) -> Optional[tuple[int, int, int]]:
    """Median screen color from the four edges, or None when the border is not a plate.

    Prefer the median of border pixels already within ``threshold`` of
    ``key_color`` (pure green) when those pixels are at least half the border.
    Otherwise use the median of the whole border, but only if that color is
    still a green screen. A red, gray, or photographic border returns None
    and the caller must not key.
    """
    height, width = bgr.shape[:2]
    band = _border_band_thickness(height, width)
    mask = np.zeros((height, width), dtype=bool)
    mask[:band, :] = True
    mask[height - band :, :] = True
    mask[:, :band] = True
    mask[:, width - band :] = True
    border = bgr[mask]
    if border.size == 0:
        return None

    dist = _bgr_distance(border, key_color)
    near = border[dist <= float(threshold)]
    if near.shape[0] * 2 >= border.shape[0]:
        chosen = np.median(near, axis=0)
    else:
        chosen = np.median(border, axis=0)
        rounded = (
            int(round(float(chosen[0]))),
            int(round(float(chosen[1]))),
            int(round(float(chosen[2]))),
        )
        near_ref = float(_bgr_distance(np.asarray([rounded], dtype=np.int32), key_color)[0])
        if near_ref > float(threshold) and not _looks_like_greenscreen_bgr(rounded):
            return None
        return rounded
    return (
        int(round(float(chosen[0]))),
        int(round(float(chosen[1]))),
        int(round(float(chosen[2]))),
    )


def chroma_key_rgba(
    rgba_bgr: np.ndarray,
    key_color: tuple[int, int, int] = GREEN_KEY_BGR,
    threshold: int = 80,
    softness: int = 20,
) -> np.ndarray:
    """
    Make an edge-connected green screen transparent without cutting interior green.

    The screen color is sampled from the frame border (see
    :func:`_sample_edge_screen_bgr`), not assumed to be exactly ``key_color``.
    Distance and the softness ramp still use ``threshold`` / ``softness``, but
    they are measured against that sampled color. Only pixels that can reach
    the outer rim through similarly colored pixels are keyed, so a green
    costume that does not touch the rim stays opaque.

    The keyed alpha is combined with ``np.minimum`` against the alpha already
    in ``rgba_bgr``. A SAM2 matte therefore stays the silhouette: chroma can
    only make pixels more transparent, and cannot paint the background back
    on. When the input alpha is fully opaque (no SAM2), this pass alone
    removes the plate. If the border does not look like a green screen, the
    alpha channel is left unchanged.

    Args:
        rgba_bgr: HxWx4 uint8 array in BGR channel order.
        key_color: Reference BGR green used to accept a near-pure border.
        threshold: Distance below which a reached pixel becomes alpha 0.
        softness: Distance band over which alpha ramps from 0 to 255.

    Returns:
        New HxWx4 uint8 RGBA array. Color channels are copied.
    """
    out = rgba_bgr.copy()
    if out.ndim != 3 or out.shape[2] < 4 or out.shape[0] == 0 or out.shape[1] == 0:
        return out

    screen = _sample_edge_screen_bgr(out[:, :, :3], key_color, threshold)
    if screen is None:
        return out

    dist = _bgr_distance(out[:, :, :3], screen)
    limit = float(threshold if softness <= 0 else threshold + softness)
    keyable = dist < limit
    if not np.any(keyable):
        return out

    count, labels = cv2.connectedComponents(keyable.astype(np.uint8), connectivity=4)
    if count <= 1:
        return out
    rim = np.zeros(keyable.shape, dtype=bool)
    rim[0, :] = True
    rim[-1, :] = True
    rim[:, 0] = True
    rim[:, -1] = True
    reached_ids = np.unique(labels[rim])
    reached_ids = reached_ids[reached_ids > 0]
    if reached_ids.size == 0:
        return out
    reached = np.isin(labels, reached_ids)

    if softness <= 0:
        keyed = np.where(reached, 0, 255).astype(np.uint8)
    else:
        ramp = np.clip((dist - float(threshold)) * 255.0 / float(softness), 0.0, 255.0)
        keyed = np.where(reached, ramp, 255.0).astype(np.uint8)
    out[:, :, 3] = np.minimum(out[:, :, 3], keyed)
    return out


def _estimate_plate_chroma(
    frame_paths: list[str],
    *,
    max_samples: int = 24,
    min_pixels: int = 500,
    hue_min: int = 30,
    hue_max: int = 110,
    sat_min: int = 60,
) -> Optional[tuple[float, float]]:
    """Lock one plate chroma for a whole clip, sampled from green-looking pixels.

    Per-frame border sampling follows the light while the clip runs: once the
    generated plate darkens, or the character touches the frame edge, the
    sampled colour drifts and the key either eats the character or leaves the
    plate behind. Voting over the green-hue pixels of many frames and taking
    the median Cr/Cb gives one stable plate colour for the sequence.

    Chroma is used rather than BGR because it ignores plate brightness: a
    cyclorama floor lit differently from its wall keeps the same Cr/Cb.

    Returns ``None`` when no frame has enough green pixels to vote.
    """
    if not frame_paths:
        return None
    step = max(1, len(frame_paths) // max(1, max_samples))
    samples: list[np.ndarray] = []
    for path in frame_paths[::step]:
        image = _read_image(path, cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            continue
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        green = (
            (hsv[:, :, 0] >= hue_min)
            & (hsv[:, :, 0] <= hue_max)
            & (hsv[:, :, 1] >= sat_min)
        )
        if int(green.sum()) < min_pixels:
            continue
        ycc = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
        samples.append(np.median(ycc[green][:, 1:].astype(np.float32), axis=0))
    if not samples:
        return None
    median = np.median(np.stack(samples), axis=0)
    return float(median[0]), float(median[1])


def chroma_key_rgba_locked(
    rgba_bgr: np.ndarray,
    plate_chroma: tuple[float, float],
    *,
    threshold: float = 14.0,
    softness: float = 5.0,
    despill: bool = True,
    min_island: int = 300,
) -> np.ndarray:
    """Key a green plate against one fixed Cr/Cb, then clean up the matte.

    Same contract as :func:`chroma_key_rgba` (only edge-connected plate pixels
    become transparent, and the existing alpha can only shrink), with three
    changes that matter for generated footage:

    1. Distance is measured in YCrCb chroma, so a plate that darkens or
       brightens between frames still matches. ``threshold`` / ``softness``
       are chroma units here, not BGR units.
    2. The matte is cleaned: a 3x3 open drops speckle, a 7x7 close fills
       pinholes, components below ``min_island`` are dropped, and a 1 px
       erosion plus a small blur pulls the edge in so the plate halo along the
       silhouette does not travel with the sprite.
    3. Green spill on the surviving pixels is pushed back toward neutral
       (``G`` clamped to the mean of ``R`` and ``B`` plus a small margin), so
       the sprite does not carry a green fringe onto the Blender plane.

    Args:
        rgba_bgr: HxWx4 uint8 array in BGR channel order.
        plate_chroma: ``(Cr, Cb)`` of the plate, from
            :func:`_estimate_plate_chroma`.
        threshold: Chroma distance below which a reached pixel becomes 0.
        softness: Chroma band over which alpha ramps from 0 to 255.
        despill: Whether to suppress green spill on kept pixels.
        min_island: Drop matte islands smaller than this many pixels (0 = off).

    Returns:
        New HxWx4 uint8 RGBA array.
    """
    out = rgba_bgr.copy()
    if out.ndim != 3 or out.shape[2] < 4 or out.shape[0] == 0 or out.shape[1] == 0:
        return out

    plate = np.asarray(plate_chroma, dtype=np.float32)
    ycc = cv2.cvtColor(out[:, :, :3], cv2.COLOR_BGR2YCrCb).astype(np.float32)
    dist = np.sqrt(np.sum((ycc[:, :, 1:] - plate) ** 2, axis=-1))
    reach_limit = float(threshold) + max(0.0, float(softness))
    keyable = dist < reach_limit
    if not np.any(keyable):
        return out

    count, labels = cv2.connectedComponents(keyable.astype(np.uint8), connectivity=4)
    if count <= 1:
        return out
    rim = np.zeros(keyable.shape, dtype=bool)
    rim[0, :] = True
    rim[-1, :] = True
    rim[:, 0] = True
    rim[:, -1] = True
    reached_ids = np.unique(labels[rim])
    reached_ids = reached_ids[reached_ids > 0]
    if reached_ids.size == 0:
        return out
    reached = np.isin(labels, reached_ids)

    if softness <= 0:
        keyed = np.where(reached, 0, 255).astype(np.uint8)
    else:
        ramp = np.clip(
            (dist - float(threshold)) * 255.0 / float(softness), 0.0, 255.0
        )
        keyed = np.where(reached, ramp, 255.0).astype(np.uint8)

    alpha = keyed
    if min_island > 0:
        fg = (alpha > 128).astype(np.uint8)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        n_lab, lab, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
        keep = np.zeros_like(fg)
        for idx in range(1, n_lab):
            if stats[idx, cv2.CC_STAT_AREA] >= int(min_island):
                keep[lab == idx] = 1
        alpha = np.where(keep > 0, alpha, 0).astype(np.uint8)

    solid = cv2.erode((alpha > 0).astype(np.uint8), np.ones((3, 3), np.uint8))
    alpha = (
        alpha.astype(np.float32) * (0.5 + 0.5 * solid.astype(np.float32))
    ).clip(0, 255).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.9)

    out[:, :, 3] = np.minimum(out[:, :, 3], alpha)

    if despill:
        kept = out[:, :, 3] > 0
        b = out[:, :, 0].astype(np.int16)
        g = out[:, :, 1].astype(np.int16)
        r = out[:, :, 2].astype(np.int16)
        cap = ((r + b) // 2 + 12).clip(0, 255)
        spill = kept & (g > cap)
        out[:, :, 1] = np.where(spill, cap, g).astype(np.uint8)

    return out


def _read_image(path: str, flags: int) -> Optional[np.ndarray]:
    """Load an image from a path OpenCV's ``imread`` cannot open.

    On Windows, ``cv2.imread`` / ``cv2.imwrite`` use the ANSI code page and
    fail for directories such as ``白发角色``. Decoding the file bytes avoids that.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        logger.warning("[motion_extractor] failed to read %s: %s", path, e)
        return None
    if not raw:
        return None
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), flags)
    return image


def _write_image(path: str, image: np.ndarray) -> bool:
    """Write an image to ``path``, including non-ASCII Windows paths."""
    dest = Path(path)
    ext = dest.suffix or ".png"
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        return False
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(buf.tobytes())
        tmp.replace(dest)
    except OSError as e:
        logger.warning("[motion_extractor] failed to write %s: %s", path, e)
        return False
    finally:
        if tmp.exists():
            tmp.unlink()
    return True


def segmented_png_name(frame_path: str, ordinal: int) -> str:
    """Return ``seg_0001.png``-style name for one extracted frame.

    Uses the trailing number in ``frame_0001.png`` when present so output
    order matches ffmpeg's 1-based frame index. ``ordinal`` is the 1-based
    position in the extracted list and is only used when the name has no digits.
    """
    stem = Path(frame_path).stem
    end = len(stem)
    start = end
    while start > 0 and stem[start - 1].isdigit():
        start -= 1
    number = int(stem[start:end]) if start < end else ordinal
    return f"seg_{number:04d}.png"


def frame_background_is_greenscreen(
    frame_path: str,
    key_color: tuple[int, int, int] = GREEN_KEY_BGR,
    threshold: int = 80,
    *,
    min_ratio: float = 0.7,
) -> bool:
    """True when the frame border looks like a green screen.

    Reuses :func:`_sample_edge_screen_bgr` so off-pure plates are accepted,
    not just borders within ``threshold`` of ``key_color``: a dark green
    curtain (e.g. BGR (77, 148, 93)) passes the hue / channel-lead checks in
    :func:`_looks_like_greenscreen_bgr` even though its distance to pure
    green exceeds ``threshold``. Character pixels in the middle do not
    count, so a person on a flat green plate still matches. A red, gray, or
    photographic border returns False.

    ``min_ratio`` is kept for backward compatibility with the original
    ratio-based implementation; the sampling logic does not use it.
    """
    image = _read_image(frame_path, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        return False
    return _sample_edge_screen_bgr(image[:, :, :3], key_color, threshold) is not None


def chroma_key_frames_sequence(
    frame_paths: list[str],
    output_dir: str,
    *,
    chroma_threshold: int = 80,
    chroma_softness: int = 20,
    lock_plate: bool = False,
    despill: bool = False,
) -> list[str]:
    """Chroma-key each frame to an RGBA PNG named ``seg_0001.png``, ``seg_0002.png``, ...

    Written even when SAM2 is not loaded. Unreadable frames are skipped.

    ``lock_plate`` estimates one Cr/Cb plate for the whole clip
    (:func:`_estimate_plate_chroma`) and keys every frame against it with
    :func:`chroma_key_rgba_locked`; this is the path the motion pipeline uses,
    because per-frame border sampling drifts once the generated plate darkens.
    When the lock cannot be estimated, per-frame border sampling is used.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    plate: Optional[tuple[float, float]] = None
    if lock_plate:
        plate = _estimate_plate_chroma(frame_paths)
        if plate is None:
            logger.info(
                "[motion_extractor] no green plate to lock; "
                "falling back to per-frame border sampling"
            )
        else:
            logger.info(
                "[motion_extractor] locked plate chroma Cr=%.1f Cb=%.1f over %d frames",
                plate[0],
                plate[1],
                len(frame_paths),
            )

    written: list[str] = []
    for ordinal, frame_path in enumerate(frame_paths, start=1):
        image = _read_image(frame_path, cv2.IMREAD_COLOR)
        out_file = output_path / segmented_png_name(frame_path, ordinal)
        if image is None:
            logger.warning("[motion_extractor] chroma key skipped unreadable frame %s", frame_path)
            continue

        height, width = image.shape[:2]
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        rgba[:, :, :3] = image[:, :, :3]
        rgba[:, :, 3] = 255
        if plate is not None:
            rgba = chroma_key_rgba_locked(rgba, plate, despill=despill)
        else:
            rgba = chroma_key_rgba(
                rgba,
                key_color=GREEN_KEY_BGR,
                threshold=chroma_threshold,
                softness=chroma_softness,
            )
        if not _write_image(str(out_file), rgba):
            logger.warning("[motion_extractor] failed to write chroma key %s", out_file)
            continue
        written.append(str(out_file))

    logger.info(
        "[motion_extractor] Chroma-keyed %d/%d frames into %s",
        len(written),
        len(frame_paths),
        output_dir,
    )
    return written


def _refine_chroma_edges_with_sam2(
    frame_paths: list[str],
    output_dir: str,
    sam2_model,
    *,
    feather_edges: bool = True,
    chroma_threshold: int = 80,
    chroma_softness: int = 20,
    snap_distance: int = 8,
) -> int:
    """Tighten chroma-keyed ``seg_*.png`` edges with the existing SAM2 segmenter.

    SAM2 runs after the chroma key. Its mask (with optional Canny feathering)
    is intersected with the chroma alpha, so green stays transparent and
    non-person pixels SAM2 rejects are cleared too. A failed SAM2 frame keeps
    the chroma-keyed PNG. The file on disk stays a 4-channel PNG.
    """
    import os
    import tempfile

    output_path = Path(output_dir)
    refined = 0
    for ordinal, frame_path in enumerate(frame_paths, start=1):
        out_file = output_path / segmented_png_name(frame_path, ordinal)
        if not out_file.is_file():
            continue

        fd, tmp_name = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        tmp_file = Path(tmp_name)
        try:
            ok = segment_person_from_frame(
                frame_path,
                str(tmp_file),
                sam2_model,
                feather_edges=feather_edges,
                greenscreen=False,
                chroma_threshold=chroma_threshold,
                chroma_softness=chroma_softness,
                snap_distance=snap_distance,
            )
            if not ok:
                continue

            chroma = _read_image(str(out_file), cv2.IMREAD_UNCHANGED)
            sam = _read_image(str(tmp_file), cv2.IMREAD_UNCHANGED)
            if (
                chroma is None
                or sam is None
                or chroma.ndim != 3
                or sam.ndim != 3
                or chroma.shape[2] != 4
                or sam.shape[2] != 4
                or chroma.shape[:2] != sam.shape[:2]
            ):
                logger.warning(
                    "[motion_extractor] SAM2 edge refine skipped for %s",
                    frame_path,
                )
                continue

            chroma[:, :, 3] = np.minimum(chroma[:, :, 3], sam[:, :, 3])
            if not _write_image(str(out_file), chroma):
                logger.warning("[motion_extractor] failed to write refined %s", out_file)
                continue
            refined += 1
        finally:
            if tmp_file.exists():
                tmp_file.unlink()

    logger.info(
        "[motion_extractor] SAM2 refined edges on %d/%d chroma-keyed frames",
        refined,
        len(frame_paths),
    )
    return refined


# ── Frame Stabilization ─────────────────────────────────────────────────────

def stabilize_segmented_frames(
    frame_paths: list[str],
    output_dir: Optional[str] = None,
    *,
    anchor_x: float = 0.5,
    anchor_y: float = 0.95,
) -> list[str]:
    """Pin the character inside each segmented RGBA frame so all apparent
    motion can be delegated to the Blender plane.

    MiniMax / video-provider footage lets the person drift within the frame
    (position and distance change), so after chroma keying every ``seg_*.png``
    has a differently placed, differently sized silhouette. This pass:

    1. Measures the person bounding box (``alpha > 0``) per frame.
    2. Normalises size: every bounding box is rescaled (aspect-preserving,
       LANCZOS) to the *median* bounding-box height of the whole sequence,
       so the person no longer grows/shrinks frame to frame.
    3. Re-anchors: the scaled sprite is pasted onto a fresh transparent
       canvas of the original size such that the bounding-box bottom centre
       (the feet) lands exactly at ``(anchor_x * W, anchor_y * H)``. Paste
       offsets are integer pixels; content shifted outside the canvas is
       clipped and vacated area stays ``alpha = 0``.

    Frames with no alpha pixels are written through unchanged and logged.
    Pure numpy/OpenCV — no models involved.

    Args:
        frame_paths: Segmented RGBA PNG sequence (``seg_0001.png`` ...).
        output_dir: Destination directory. ``None`` writes to a
            ``stabilized/`` subdirectory next to the input frames. File
            names are preserved, so passing the source directory itself
            overwrites the frames in place (the pipeline does this).
        anchor_x / anchor_y: Normalised canvas coordinates of the feet
            anchor (default: horizontally centred, 95% down the frame).

    Returns:
        List of written file paths.
    """
    paths = [str(p) for p in frame_paths]
    if not paths:
        return []
    if output_dir is None:
        output_dir = str(Path(paths[0]).parent / "stabilized")
    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    # Pass 1: read every frame and measure the person bounding box.
    images: list[Optional[np.ndarray]] = []
    bboxes: list[Optional[tuple[int, int, int, int]]] = []
    heights: list[int] = []
    for p in paths:
        img = _read_image(p, cv2.IMREAD_UNCHANGED)
        images.append(img)
        bbox = None
        if img is not None and img.ndim == 3 and img.shape[2] == 4:
            alpha = img[:, :, 3]
            ys, xs = np.nonzero(alpha > 0)
            if ys.size > 0:
                y0, y1 = int(ys.min()), int(ys.max()) + 1
                x0, x1 = int(xs.min()), int(xs.max()) + 1
                bbox = (y0, y1, x0, x1)
                heights.append(y1 - y0)
        bboxes.append(bbox)

    target_h = int(round(float(np.median(heights)))) if heights else 0
    if target_h > 0:
        logger.info(
            "[motion_extractor] stabilize: %d/%d frames have alpha; median bbox height=%d",
            len(heights),
            len(paths),
            target_h,
        )

    # Pass 2: scale to the median height, then paste with the feet anchored.
    written: list[str] = []
    for p, img, bbox in zip(paths, images, bboxes):
        dest = out_dir_path / Path(p).name
        if img is None:
            logger.warning("[motion_extractor] stabilize skipped unreadable frame %s", p)
            continue
        if bbox is None or target_h <= 0:
            logger.info(
                "[motion_extractor] stabilize: no alpha pixels in %s; written unchanged",
                p,
            )
            if not _write_image(str(dest), img):
                logger.warning("[motion_extractor] failed to write stabilized %s", dest)
                continue
            written.append(str(dest))
            continue

        y0, y1, x0, x1 = bbox
        crop = img[y0:y1, x0:x1]
        src_h, src_w = crop.shape[:2]
        scale = target_h / float(src_h)
        new_w = max(1, int(round(src_w * scale)))
        if src_h == target_h and src_w == new_w:
            sprite = crop
        else:
            sprite = cv2.resize(crop, (new_w, target_h), interpolation=cv2.INTER_LANCZOS4)

        height, width = img.shape[:2]
        canvas = np.zeros((height, width, 4), dtype=np.uint8)
        foot_x = int(round(anchor_x * width))
        foot_y = int(round(anchor_y * height))
        # Integer-pixel translation: sprite bottom centre lands on the anchor.
        paste_x = foot_x - new_w // 2
        paste_y = foot_y - target_h
        src_x0 = max(0, -paste_x)
        src_y0 = max(0, -paste_y)
        dst_x0 = max(0, paste_x)
        dst_y0 = max(0, paste_y)
        copy_w = min(new_w - src_x0, width - dst_x0)
        copy_h = min(target_h - src_y0, height - dst_y0)
        if copy_w > 0 and copy_h > 0:
            canvas[dst_y0 : dst_y0 + copy_h, dst_x0 : dst_x0 + copy_w] = sprite[
                src_y0 : src_y0 + copy_h, src_x0 : src_x0 + copy_w
            ]

        if not _write_image(str(dest), canvas):
            logger.warning("[motion_extractor] failed to write stabilized %s", dest)
            continue
        written.append(str(dest))

    logger.info(
        "[motion_extractor] Stabilized %d/%d frames into %s (anchor=%.2f,%.2f)",
        len(written),
        len(paths),
        output_dir,
        anchor_x,
        anchor_y,
    )
    return written


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
    When ``greenscreen`` is True an additional chroma-key pass runs on the
    SAM2 alpha. Edge-connected screen pixels become transparent.
    :func:`chroma_key_rgba` keeps the more transparent of the two alphas, so
    the SAM2 silhouette is not painted back on. Green cloth that does not
    touch the frame edge stays opaque.

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

        image = _read_image(frame_path, cv2.IMREAD_COLOR)
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

        return _write_image(output_path, rgba)

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
        safe_char = slugify(character_name, fallback="character")
        safe_action = slugify(action_name, fallback="action")
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
            provider and chroma-key extracted frames into RGBA PNGs
            (``seg_0001.png`` …). A green border on the frames is treated the
            same way when this flag is false. SAM2, if loaded, refines those
            edges afterwards. Once the video and frames exist, a missing SAM2
            model leaves ``status`` as ``"done"`` and ``error`` unset.
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

    safe_char = slugify(character_name, fallback="character")
    safe_action = slugify(action_prompt, fallback="action")
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

    # 3. Chroma-key green plates, then optionally refine edges with SAM2.
    # Video and frames already exist, so a missing SAM2 model is not a failure.
    if sam2_model is None:
        try:
            from app.models import model_manager
            if model_manager.is_loaded():
                sam2_model = model_manager.sam2
        except Exception:
            pass

    use_chroma = bool(greenscreen)
    if not use_chroma:
        try:
            use_chroma = frame_background_is_greenscreen(
                frames[0],
                threshold=chroma_threshold,
            )
        except Exception as e:
            logger.warning("[motion_extractor] greenscreen detection failed: %s", e)
            use_chroma = False
        if use_chroma:
            logger.info(
                "[motion_extractor] Frame background looks like a green screen; applying chroma key"
            )

    if use_chroma:
        chroma_key_frames_sequence(
            frames,
            motion.segmented_dir,
            chroma_threshold=chroma_threshold,
            chroma_softness=chroma_softness,
            lock_plate=True,
            despill=True,
        )

    if sam2_model and use_chroma:
        _refine_chroma_edges_with_sam2(
            frames,
            motion.segmented_dir,
            sam2_model,
            feather_edges=feather_edges,
            chroma_threshold=chroma_threshold,
            chroma_softness=chroma_softness,
            snap_distance=snap_distance,
        )
    elif sam2_model:
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
    elif use_chroma:
        logger.info(
            "[motion_extractor] SAM2 model not available; using greenscreen chroma key only"
        )
    else:
        logger.info(
            "[motion_extractor] SAM2 model not available; leaving extracted frames unsegmented"
        )

    # 4. Stabilize the keyed sequence: pin the in-frame character (feet
    # anchored, size normalised) so all lateral motion is owned by the
    # Blender plane. seg_*.png are overwritten in place, so the files later
    # copied into the project motions/ dir are already stabilized.
    seg_frames = sorted(Path(motion.segmented_dir).glob("seg_*.png"))
    if seg_frames:
        try:
            stabilize_segmented_frames(
                [str(p) for p in seg_frames],
                motion.segmented_dir,
            )
        except Exception as e:
            logger.warning("[motion_extractor] stabilize_segmented_frames failed: %s", e)

    motion.status = "done"
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
