"""
Depth-based layer segmentation utilities.

Uses percentile-based thresholds on the depth map to segment the image into
discrete depth layers (near / mid-near / mid / mid-far / far).
Each layer becomes a binary mask indicating which pixels belong to it.

No external ML dependencies — uses only numpy.
"""

import numpy as np


def compute_depth_layer_bounds(
    depth_m: np.ndarray,
    n_layers: int = 5,
) -> list[tuple[float, float]]:
    """
    Segment a depth map into N depth layers using percentile thresholds.

    Divides the depth range into equal-size percentile buckets, then uses
    the bucket boundaries as layer thresholds. This is fast, deterministic,
    and requires no ML libraries.

    Args:
        depth_m: HxW numpy array of depth in meters.
        n_layers: Number of depth layers (default 5).

    Returns:
        A list of (z_min, z_max) tuples, sorted from near to far:
        [(0, z0), (z0, z1), ..., (z_{n-2}, INF)]
        The last layer has z_max = INF (unbounded).
    """
    valid = depth_m[~np.isnan(depth_m)]
    if valid.size == 0:
        # Fallback: equal spacing from 0 to max
        d_min, d_max = 0.0, float(depth_m.max())
    else:
        d_min, d_max = float(valid.min()), float(valid.max())

    # Build percentile boundaries: 0%, 20%, 40%, 60%, 80%, 100%
    # then use the actual pixel values at those percentiles
    percentiles = np.linspace(0, 100, n_layers + 1)  # [0, 20, 40, 60, 80, 100]
    thresholds = np.percentile(depth_m, percentiles)

    # np.unique deduplicates identical thresholds (flat regions → same value for
    # multiple percentiles). If deduplication happened, all pixels have the same
    # depth — create artificial layer boundaries by spreading from d_min.
    unique_thresh = np.unique(thresholds)
    if len(unique_thresh) < len(thresholds):
        # Use a spread proportional to d_max so layers have meaningful width.
        # For flat depth (d_min==d_max) this creates distinct layer boundaries.
        spread = max(d_max - d_min, 1.0)
        all_vals = np.linspace(d_min, d_min + spread, n_layers + 1)
        thresholds = np.sort(all_vals)

    # Build (z_min, z_max) bounds from thresholds
    # Ensure minimum layer width to avoid degenerate zero-width layers
    MIN_WIDTH = 0.01  # meters
    bounds: list[tuple[float, float]] = []
    for i in range(len(thresholds) - 1):
        z_lo = float(thresholds[i])
        z_hi = float(thresholds[i + 1])
        if z_hi - z_lo < MIN_WIDTH:
            z_hi = z_lo + MIN_WIDTH
        bounds.append((z_lo, z_hi))
    bounds.append((float(thresholds[-1]), float("inf")))

    return bounds


def create_layer_masks(
    depth_m: np.ndarray,
    depth_bounds: list[tuple[float, float]],
) -> list[np.ndarray]:
    """
    Create a binary mask for each depth layer.

    Args:
        depth_m: HxW depth array in meters.
        depth_bounds: List of (z_min, z_max) tuples from compute_depth_layer_bounds.

    Returns:
        List of HxW uint8 masks (0 or 255), one per layer.
    """
    masks = []
    for z_min, z_max in depth_bounds:
        if z_max == float("inf"):
            mask = (depth_m >= z_min).astype(np.uint8) * 255
        else:
            mask = ((depth_m >= z_min) & (depth_m < z_max)).astype(np.uint8) * 255
        masks.append(mask)
    return masks


def assign_mask_to_layer(
    depth_m: np.ndarray,
    mask: np.ndarray,
    depth_bounds: list[tuple[float, float]],
) -> int:
    """
    Determine which depth layer a mask belongs to.

    Finds the median depth of pixels inside the mask, then returns the
    index of the layer whose [z_min, z_max) range contains that depth.

    Args:
        depth_m: HxW depth array in meters.
        mask: HxW bool mask.
        depth_bounds: List of (z_min, z_max) tuples.

    Returns:
        Layer index (0 = nearest, len(depth_bounds)-1 = farthest).
        Returns 0 if no valid depth is found.
    """
    masked_depth = np.where(mask, depth_m, np.nan)
    median_depth = float(np.nanmedian(masked_depth))

    if np.isnan(median_depth):
        return 0

    for i, (z_min, z_max) in enumerate(depth_bounds):
        if z_max == float("inf"):
            if median_depth >= z_min:
                return i
        else:
            if z_min <= median_depth < z_max:
                return i

    return len(depth_bounds) - 1
