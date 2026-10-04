"""
Ground plane reconstruction.

The goal: turn a 2D street/indoor scene image into a parametric ground plane
the Blender plugin can use directly, instead of a perspective-distorted PNG.

Steps:

1. **Ground mask** — start with the union of GroundingDINO+SAM2 detections whose
   ``label`` belongs to ``object_detector.GROUND_CLASSES``. Fall back to a
   "bottom half of image" mask when no detection survived (so we never crash
   on a pure-nature scene where GroundingDINO missed the grass).

2. **Backproject to 3D** — for every pixel inside the mask, convert ``(u, v,
   depth)`` to a 3D ray / world point using a pinhole camera intrinsics matrix
   ``K``. ``K`` defaults to ``focal = 1.2 * max(w, h)``, principal point at
   the image centre.

3. **RANSAC plane fit** — pick 3 random in-mask points, fit a plane
   ``ax + by + cz + d = 0`` (least squares), count inliers within ``threshold``
   metres of the plane, iterate. 200 is enough for a street scene.

4. **Depth correction** — re-project every ground-mask pixel onto the fitted
   plane (along the camera ray) and write the corrected depth into an H×W
   float array. Outside the mask, leave the original depth untouched. This is
   the input Blender's depth-aware shader reads so a 3D camera push-in doesn't
   show ground stretching.

5. **Cutout RGBA** — combine original RGB with the ground mask → transparent
   everywhere else. Blender reads this as a texture for the ground plane mesh
   sized to the plane's screen-space bbox.

Failure modes (we return ``None`` instead of crashing):

- No detections AND no in‑image fallback feasible → ``None``
- Mask has < 100 pixels → ``None``
- RANSAC best inlier ratio < 0.30 → ``None``
- Resulting normal vector not roughly upward (|normal.y| < 0.3) → ``None``
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np
from PIL import Image

from app.services.object_assets import (
    GroundAsset,
    bbox_of_mask,
    make_object_rgba,
)
from app.services.object_detector import GROUND_CLASSES

logger = logging.getLogger("aicss.ground_reconstructor")


# ──────────────────────────────────────────────────────────────────────────────
# Camera intrinsics
# ──────────────────────────────────────────────────────────────────────────────


def default_intrinsics(width: int, height: int) -> np.ndarray:
    """Build a pinhole intrinsics matrix from image size.

    Focal length ``focal = 1.2 * max(w, h)`` is a reasonable default for
    natural images (matches the 35 mm full-frame equivalent). Principal point
    is at the image centre. Used when the caller didn't pass a calibrated K.
    """
    focal = 1.2 * float(max(width, height))
    cx = width / 2.0
    cy = height / 2.0
    K = np.array([
        [focal, 0.0,   cx  ],
        [0.0,   focal, cy  ],
        [0.0,   0.0,   1.0 ],
    ], dtype=np.float64)
    return K


def backproject(depth_meters: np.ndarray, K: np.ndarray) -> np.ndarray:
    """Convert an H×W depth map to H×W×3 world points using pinhole K.

    Returns float64 array of shape (H, W, 3). Pixels with depth <= 0 (i.e.
    "no measurement") yield (0, 0, 0).
    """
    H, W = depth_meters.shape
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    us, vs = np.meshgrid(np.arange(W), np.arange(H))
    z = depth_meters.astype(np.float64)
    x = (us - cx) * z / fx
    y = (vs - cy) * z / fy
    pts = np.stack([x, y, z], axis=-1)
    # Mask invalid depth
    pts[z <= 0] = 0.0
    return pts


def project_to_plane(pts: np.ndarray, plane: dict) -> np.ndarray:
    """Project each 3D point onto the plane along the camera ray (origin→point).

    Plane: ``a*x + b*y + c*z + d = 0``. The ray from origin to point P hits the
    plane at ``t * P`` where ``t = -d / (a*P.x + b*P.y + c*P.z)``.
    """
    a, b, c, d = plane["a"], plane["b"], plane["c"], plane["d"]
    px, py, pz = pts[..., 0], pts[..., 1], pts[..., 2]
    denom = a * px + b * py + c * pz
    # Avoid divide-by-zero; valid denom means the ray isn't parallel to plane.
    valid = np.abs(denom) > 1e-9
    t = np.zeros_like(denom)
    t[valid] = -d / denom[valid]
    # Projected depth along z-axis (camera looks down -z in OpenCV convention,
    # but for our purposes what matters is |projected| since Blender interprets
    # the depth image along its own camera axis).
    proj_z = np.abs(t * pz)
    proj_z[~valid] = 0.0
    return proj_z


# ──────────────────────────────────────────────────────────────────────────────
# RANSAC plane fit
# ──────────────────────────────────────────────────────────────────────────────


def fit_plane_least_squares(pts: np.ndarray) -> Optional[dict]:
    """Fit a plane through N×3 points via SVD. Returns ``{"a","b","c","d"}`` or None.

    The plane normal is taken to be the singular vector of ``pts - mean(pts)``
    with the smallest singular value; signs are flipped so that ``b >= 0``
    (i.e. the normal points roughly upward when +y is up).
    """
    if pts.shape[0] < 3:
        return None
    centroid = pts.mean(axis=0)
    centered = pts - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    normal = vh[-1]  # smallest singular vector → normal
    if normal[1] < 0:
        normal = -normal
    a, b, c = float(normal[0]), float(normal[1]), float(normal[2])
    d = -float(np.dot(normal, centroid))
    return {"a": a, "b": b, "c": c, "d": d}


def ransac_fit_plane(
    pts: np.ndarray,
    threshold: float = 0.05,
    iters: int = 200,
    rng: Optional[np.random.Generator] = None,
) -> tuple[Optional[dict], np.ndarray]:
    """RANSAC plane fit. Returns (best_plane_or_None, inlier_mask)."""
    rng = rng or np.random.default_rng()
    n = pts.shape[0]
    if n < 3:
        return None, np.zeros(n, dtype=bool)
    best_plane: Optional[dict] = None
    best_inliers = np.zeros(n, dtype=bool)
    best_count = 0
    for _ in range(iters):
        idx = rng.choice(n, size=3, replace=False)
        sample = pts[idx]
        plane = fit_plane_least_squares(sample)
        if plane is None:
            continue
        a, b, c, d = plane["a"], plane["b"], plane["c"], plane["d"]
        denom = np.sqrt(a * a + b * b + c * c) + 1e-12
        dist = np.abs(a * pts[:, 0] + b * pts[:, 1] + c * pts[:, 2] + d) / denom
        inliers = dist < threshold
        cnt = int(inliers.sum())
        if cnt > best_count:
            best_count = cnt
            best_inliers = inliers
            best_plane = plane
    if best_plane is not None and best_inliers.sum() >= 3:
        # Refit on the full inlier set so the final plane uses all good points.
        refined = fit_plane_least_squares(pts[best_inliers])
        if refined is not None:
            best_plane = refined
    return best_plane, best_inliers


# ──────────────────────────────────────────────────────────────────────────────
# Fallback mask
# ──────────────────────────────────────────────────────────────────────────────


def fallback_ground_mask(width: int, height: int, depth_meters: np.ndarray) -> np.ndarray:
    """When no GroundingDINO detection hit a ground class, use the bottom-half
    of the image, filtered to "near" pixels.

    This is a coarse fallback — we only use it when the user explicitly
    opted out of detection or GroundingDINO missed every ground noun. RANSAC
    on this rough mask often still converges to a reasonable floor plane.
    """
    H, W = depth_meters.shape
    mask = np.zeros((H, W), dtype=bool)
    if H == 0:
        return mask
    # Bottom half.
    y_start = int(H * 0.55)
    mask[y_start:] = True
    # Prefer near pixels: depth < median + 0.5 * median.
    if depth_meters is not None and depth_meters.shape == (H, W):
        valid = depth_meters > 0
        if valid.any():
            med = float(np.median(depth_meters[valid]))
            near = depth_meters < (med + max(med * 0.5, 1.0))
            mask &= near
    return mask


# ──────────────────────────────────────────────────────────────────────────────
# Top-level reconstructor
# ──────────────────────────────────────────────────────────────────────────────


def reconstruct_ground(
    image: Image.Image,
    depth_meters: np.ndarray,
    *,
    detections: Optional[Sequence[tuple[object, np.ndarray]]] = None,
    intrinsics: Optional[np.ndarray] = None,
    ransac_threshold: float = 0.05,
    ransac_iters: int = 200,
    min_inlier_ratio: float = 0.30,
) -> Optional[GroundAsset]:
    """Run the full ground-plane reconstruction pipeline.

    Args:
        image: PIL RGB image.
        depth_meters: (H, W) depth map in metres (or None to skip plane fitting,
            in which case we return None).
        detections: optional list of ``(detection, mask)`` pairs from
            ``object_detector``. We filter to entries whose label is in
            ``GROUND_CLASSES`` and union their masks.
        intrinsics: optional 3×3 camera matrix (default: ``default_intrinsics``).
        ransac_threshold: distance threshold in metres for plane inliers.
        ransac_iters: RANSAC iterations.
        min_inlier_ratio: if best inlier ratio < this, return None.

    Returns:
        ``GroundAsset`` or ``None`` when the pipeline rejects the scene.
    """
    if depth_meters is None:
        return None
    rgb = image.convert("RGB")
    W, H = rgb.size
    if depth_meters.shape != (H, W):
        logger.warning(
            "[ground_recon] depth shape %s != image (%d,%d); skipping",
            depth_meters.shape, H, W,
        )
        return None

    K = intrinsics if intrinsics is not None else default_intrinsics(W, H)
    if K.shape != (3, 3):
        logger.warning("[ground_recon] intrinsics must be 3x3; got %s", K.shape)
        return None

    # 1. Build the ground mask from GroundingDINO detections.
    ground_mask = np.zeros((H, W), dtype=bool)
    if detections:
        for det, mask in detections:
            label = getattr(det, "label", "").lower().strip()
            if label in GROUND_CLASSES:
                clipped = mask[:H, :W] if mask.shape != (H, W) else mask
                ground_mask |= clipped.astype(bool)

    # 2. Fallback when no detection hit a ground noun.
    if ground_mask.sum() < 100:
        fallback = fallback_ground_mask(W, H, depth_meters)
        if fallback.sum() > ground_mask.sum():
            ground_mask = fallback

    if ground_mask.sum() < 100:
        logger.info("[ground_recon] ground mask too small (%d px); skipping", int(ground_mask.sum()))
        return None

    # 3. Backproject the masked pixels to 3D.
    world_pts_full = backproject(depth_meters, K)
    mask_in_image = ground_mask & (depth_meters > 0)
    pts3d = world_pts_full[mask_in_image]
    if pts3d.shape[0] < 200:
        logger.info("[ground_recon] too few valid 3D points (%d); skipping", pts3d.shape[0])
        return None

    # 4. RANSAC plane fit.
    plane, inliers = ransac_fit_plane(
        pts3d, threshold=ransac_threshold, iters=ransac_iters
    )
    if plane is None:
        logger.info("[ground_recon] RANSAC failed to find a plane")
        return None

    inlier_ratio = float(inliers.sum()) / float(max(pts3d.shape[0], 1))
    if inlier_ratio < min_inlier_ratio:
        logger.info(
            "[ground_recon] inlier_ratio=%.2f < %.2f; rejecting plane",
            inlier_ratio, min_inlier_ratio,
        )
        return None

    # The fitted normal must be roughly upward (Blender's +Y is up).
    normal = np.array([plane["a"], plane["b"], plane["c"]], dtype=np.float64)
    norm = np.linalg.norm(normal) + 1e-12
    normal_unit = (normal / norm).tolist()
    if abs(normal_unit[1]) < 0.3:
        logger.info(
            "[ground_recon] normal %s not upward; rejecting", normal_unit,
        )
        return None

    # 5. Depth correction.
    depth_correction = np.zeros((H, W), dtype=np.float32)
    depth_correction[ground_mask] = project_to_plane(world_pts_full, plane).astype(np.float32)[ground_mask]

    # 6. Cutout RGBA.
    cutout = make_object_rgba(rgb, ground_mask, feather_px=2)  # ground spans large area, soften more

    # 7. Centroid of inlier 3D points.
    centroid = pts3d[inliers].mean(axis=0).astype(np.float64).tolist()

    bbox = bbox_of_mask(ground_mask)
    area_px = int(ground_mask.sum())
    vertical_pos = float(((bbox[1] + bbox[3]) / 2.0) / H) if H else 0.0
    meta = {
        "inlier_ratio": inlier_ratio,
        "bbox": list(bbox),
        "vertical_pos": vertical_pos,
        "area_px": area_px,
        "ransac_threshold": ransac_threshold,
    }

    return GroundAsset(
        object_id="ground",
        plane={"a": plane["a"], "b": plane["b"], "c": plane["c"], "d": plane["d"]},
        plane_normal=normal_unit,
        centroid=centroid,
        bbox=bbox,
        cutout=cutout,
        depth_correction=depth_correction,
        z_offset=-1.5,
        meta=meta,
    )