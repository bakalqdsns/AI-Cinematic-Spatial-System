"""
Layer PNG Exporter — exports each depth layer (foreground/midground/background/sky/ground)
as an independent RGBA PNG with the layer's visible region preserved and everything
else transparent.

Phase 1 deliverable: `POST /api/aicss/layers/export` endpoint, plus a helper that
scene generators can call directly to embed `layeredImages` in the scene manifest.

Per the Implementation Plan (2026-08-10), this is the P0 blocker for the Blender
plugin (Module 6) — the 4 PNGs this function produces are what the Blender plugin
imports and places at the canonical Z-axis offsets (foreground=-2, midground=-6,
background=-12, sky=-20).

Phase 2 (2026-08-17) — Object-Aware Layers
-------------------------------------------
The new bucketing strategy feeds three signals into each pixel's layer assignment:

1. ``object_assets`` — per-instance masks from GroundingDINO + SAM2. The mask
   for each object is assigned to its ``layer_hint`` (foreground / midground /
   background / ground).
2. ``ground_asset`` — the parametric ground plane produced by
   ``ground_reconstructor``. Its mask fills the dedicated ``ground`` layer.
3. ``sky_mask`` — top-half + low-saturation pixels take the ``sky`` layer,
   computed from RGB when the caller didn't provide an explicit sky mask.

All remaining pixels (i.e. outside every object mask and outside sky) fall
back to a depth-percentile bucketing scheme (P10/P50/P85) over the residual
depth distribution. This guarantees:

- The relative depth ordering of the un-anchored region stays sensible.
- The fixed ``scale=50.0`` DepthAnything assumption no longer dictates
  which depth values belong to which layer — the cut points adapt to the
  scene.

The function keeps its old signature (``export_layers(image, depth_meters, *,
layers, feather_px)``) for backwards compatibility. The new keyword arguments
(``object_assets``, ``ground_asset``, ``sky_mask``, ``sky_mask_fn``) default
to ``None``, so existing callers continue to work — they get the old
fixed-range bucketing when no anchors are supplied.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageFilter

from app.config import settings

logger = logging.getLogger("aicss.layers")


# Z-axis offsets used by the Blender plugin to space the layers along the camera
# axis. Negative Z means "closer to the camera" in Blender's right-handed
# coordinate system. These match `mesh_exporter.py`'s default layer Z values so
# a scene assembled in Three.js lines up pixel-for-pixel when re-rendered in
# Blender.
LAYER_Z_OFFSETS: dict[str, float] = {
    "foreground": -2.0,
    "midground": -6.0,
    "background": -12.0,
    "sky": -20.0,
    "ground": -1.5,
}

# Z range (depth band) that each layer covers, in meters. Matches
# `settings.depth_buckets` so the layer buckets from
# `spatial_utils.assign_to_depth_layer` align with these Z offsets. The new
# bucketing pipeline no longer relies on these for assignment (it uses
# anchors + percentiles), but the table is still emitted in the response
# for backward compatibility with the Blender plugin.
LAYER_Z_RANGES: dict[str, tuple[float, float]] = {
    "foreground": (0.0, 5.0),
    "midground": (5.0, 15.0),
    "background": (15.0, 50.0),
    "sky": (50.0, float("inf")),
    "ground": (0.0, float("inf")),
}

# Canonical render order: sky (deepest) → foreground (closest). Layers are
# emitted in this order so a 3D importer can stack planes from back to front.
# ``ground`` slots in *after* foreground so the floor sits right under the
# character / vehicle masks — visually it never covers foreground subjects.
LAYER_ORDER: tuple[str, ...] = ("sky", "background", "midground", "foreground", "ground")


# ──────────────────────────────────────────────────────────────────────────────
# Sky mask
# ──────────────────────────────────────────────────────────────────────────────


def compute_sky_mask(rgb: np.ndarray, depth_meters: Optional[np.ndarray] = None) -> np.ndarray:
    """Return a bool mask of likely sky pixels.

    Heuristic: upper half of the image AND low saturation AND high brightness.
    When the depth map is available we additionally require the pixel to be
    in the far-depth tail (>= P85 of the residual distribution) — that filters
    out a bright white building facade that would otherwise look "sky-like".
    """
    H, W = rgb.shape[:2]
    if H == 0 or W == 0:
        return np.zeros((H, W), dtype=bool)

    # Upper-half mask
    upper = np.zeros((H, W), dtype=bool)
    upper[: int(H * 0.55)] = True

    # Color mask: HSV saturation < 0.4 AND brightness > 0.5.
    img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    hsv = np.array(img.convert("HSV"), dtype=np.float32)  # H 0..255, S 0..255, V 0..255
    sat = hsv[..., 1] / 255.0
    val = hsv[..., 2] / 255.0
    color = (sat < 0.4) & (val > 0.5)

    sky = upper & color

    # Far-depth tail — only apply when we have a depth map and the mask is
    # still larger than 1% of the image (so we don't kill the entire sky in
    # flat-depth scenes where the percentile bucket is degenerate).
    if depth_meters is not None and depth_meters.shape == (H, W):
        valid = depth_meters > 0
        if valid.any():
            p85 = float(np.percentile(depth_meters[valid], 85))
            far = depth_meters >= p85
            refined = sky & far
            # If refining collapses sky to < 1% of the image, keep the loose
            # version so a flat / overexposed sky still gets separated.
            if refined.sum() > max(50, H * W * 0.01):
                sky = refined
    return sky


# ──────────────────────────────────────────────────────────────────────────────
# Core bucketing
# ──────────────────────────────────────────────────────────────────────────────


def _build_layer_masks(
    depth_meters: Optional[np.ndarray],
    object_assets: Optional[list],
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
    rgb: Optional[np.ndarray] = None,
) -> dict[str, np.ndarray]:
    """Compute per-pixel boolean masks for every layer.

    Returns a dict keyed by layer name → H×W bool. Layers absent from the
    output are not produced (callers should check before assembling RGBA).
    """
    if depth_meters is None and object_assets is None and sky_mask is None and ground_asset is None:
        # No inputs at all — caller wants the legacy fallback.
        return {}
    H, W = (depth_meters.shape if depth_meters is not None else
            (rgb.shape[0], rgb.shape[1]) if rgb is not None else
            (next(iter(object_assets)).mask.shape if object_assets else (0, 0)))

    masks: dict[str, np.ndarray] = {}

    # 1. Object masks — each object lands on its layer_hint.
    if object_assets:
        for layer in ("foreground", "midground", "background"):
            layer_mask = np.zeros((H, W), dtype=bool)
            for obj in object_assets:
                if obj.layer_hint == layer and obj.mask.shape == (H, W):
                    layer_mask |= obj.mask.astype(bool)
            if layer_mask.any():
                masks[layer] = layer_mask

    # 2. Ground mask.
    ground_mask = np.zeros((H, W), dtype=bool)
    if ground_asset is not None and getattr(ground_asset, "cutout", None) is not None:
        # We don't store the ground mask on the asset — derive it from its alpha.
        if ground_asset.cutout.size == (W, H):
            alpha = np.array(ground_asset.cutout)[..., 3]
            ground_mask = alpha > 0
    # Also accept ground-mask objects sitting inside ``object_assets``.
    if object_assets:
        for obj in object_assets:
            if obj.layer_hint == "ground" and obj.mask.shape == (H, W):
                ground_mask |= obj.mask.astype(bool)
    if ground_mask.any():
        masks["ground"] = ground_mask

    # 3. Sky mask.
    if sky_mask is None and rgb is not None and depth_meters is not None:
        sky_mask = compute_sky_mask(rgb, depth_meters)
    if sky_mask is not None and sky_mask.shape == (H, W) and sky_mask.any():
        masks["sky"] = sky_mask.astype(bool)

    # 4. Residual bucketing (depth percentiles) for everything not yet assigned.
    if depth_meters is not None and depth_meters.shape == (H, W):
        assigned = np.zeros((H, W), dtype=bool)
        for m in masks.values():
            assigned |= m
        residual_mask = (~assigned) & (depth_meters > 0)
        residual_depth = depth_meters[residual_mask]
        if residual_depth.size > 16:
            p10 = float(np.percentile(residual_depth, 10))
            p50 = float(np.percentile(residual_depth, 50))
            p85 = float(np.percentile(residual_depth, 85))
            fg_pixels = residual_mask & (depth_meters <= max(p10, 0.5))
            mg_pixels = residual_mask & (depth_meters > max(p10, 0.5)) & (depth_meters <= p50)
            bg_pixels = residual_mask & (depth_meters > p50) & (depth_meters <= p85)
            far_pixels = residual_mask & (depth_meters > p85)
            # Merge with anchor masks so we don't shrink foreground when anchors
            # already covered it.
            masks["foreground"] = masks.get("foreground", np.zeros((H, W), dtype=bool)) | fg_pixels
            masks["midground"] = masks.get("midground", np.zeros((H, W), dtype=bool)) | mg_pixels
            masks["background"] = masks.get("background", np.zeros((H, W), dtype=bool)) | bg_pixels
            # Far pixels with no sky already assigned: top up sky, dump the rest into background.
            if "sky" in masks:
                # Don't override existing sky pixels; just absorb extra far pixels into background.
                bg_extra = far_pixels & ~masks["sky"]
                masks["background"] |= bg_extra
            else:
                masks["sky"] = far_pixels
        else:
            # Residual too small — assign the whole residual to foreground (legacy behaviour).
            masks.setdefault("foreground", np.zeros((H, W), dtype=bool))
            masks["foreground"] |= residual_mask

    # 5. Front-to-back masking: object anchors must not "shrink" when the
    #    foreground-percentile bucket has nearby depth. We OR (not overwrite)
    #    so anchors stay inside their layer.
    return masks


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def export_layers(
    image: Image.Image,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
) -> dict[str, Image.Image]:
    """Return one RGBA PNG per depth layer.

    Each returned image has the same width/height as ``image``. Pixels that
    belong to the layer keep their original RGB; everything else is transparent
    (alpha = 0). With no anchors supplied this is the legacy fixed-range
    bucketing — backwards compatible with Phase 1 callers.

    Args:
        image: Original RGB scene image (any mode; will be converted to RGB).
        depth_meters: (H, W) depth map in meters, or None to skip depth-based
            bucketing. When None and no anchors are supplied, every layer
            receives a fully opaque mask.
        layers: Subset of layer names to export. Defaults to all five
            canonical layers (sky / background / midground / foreground /
            ground).
        feather_px: Edge feathering radius (in pixels). 0 = hard edges,
            1 = minimal softening. Uses Pillow's GaussianBlur on the alpha.
        object_assets: optional list of ``ObjectAsset``. Each mask is placed
            on its ``layer_hint`` before the depth-percentile pass runs.
        ground_asset: optional ``GroundAsset``. Its mask fills the ``ground``
            layer (separate from any ground-class objects in ``object_assets``).
        sky_mask: optional pre-computed (H, W) bool mask of sky pixels. When
            ``None``, ``compute_sky_mask`` runs on the supplied image.
    """
    if image is None:
        raise ValueError("image is required")

    if layers is None:
        layers = list(LAYER_ORDER)
    else:
        layers = [layer.lower() for layer in layers]

    rgb = image.convert("RGB")
    w, h = rgb.size
    rgb_np = np.array(rgb)

    if depth_meters is not None and depth_meters.shape != (h, w):
        raise ValueError(
            f"depth_meters shape {depth_meters.shape} does not match image ({h}, {w})"
        )

    # Decide whether to use the new anchor-driven pipeline or the legacy
    # fixed-range bucketing. Any of {object_assets, ground_asset, sky_mask}
    # triggers the new pipeline.
    use_anchors = bool(object_assets) or (ground_asset is not None) or (sky_mask is not None)

    layer_masks: dict[str, np.ndarray]
    if use_anchors:
        layer_masks = _build_layer_masks(
            depth_meters=depth_meters,
            object_assets=object_assets,
            ground_asset=ground_asset,
            sky_mask=sky_mask,
            rgb=rgb_np,
        )
    else:
        # Legacy path — fixed depth range bucketing (Phase 1 behaviour).
        layer_masks = {}
        for layer in layers:
            if depth_meters is not None and layer in LAYER_Z_RANGES:
                z_min, z_max = LAYER_Z_RANGES[layer]
                mask = (depth_meters >= z_min) & (depth_meters < z_max)
            else:
                mask = np.ones((h, w), dtype=bool)
            layer_masks[layer] = mask

    # Compose RGBA per layer.
    out: dict[str, Image.Image] = {}
    for layer in layers:
        mask = layer_masks.get(layer, np.zeros((h, w), dtype=bool))
        alpha = (mask.astype(np.uint8) * 255)
        alpha_img = Image.fromarray(alpha, mode="L")
        if feather_px > 0:
            blurred = alpha_img.filter(
                ImageFilter.GaussianBlur(radius=float(feather_px))
            )
            blurred_np = np.array(blurred)
            alpha = (blurred_np > 127).astype(np.uint8) * 255
            alpha_img = Image.fromarray(alpha, mode="L")
        rgba = np.dstack([rgb_np, alpha])
        out[layer] = Image.fromarray(rgba, mode="RGBA")
    return out


def export_layers_to_data_uris(
    image: Image.Image,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
    fmt: str = "PNG",
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
) -> dict[str, str]:
    """Convenience wrapper — returns ``data:image/png;base64,...`` URIs.

    Useful for embedding layer PNGs directly in JSON responses without
    persisting to disk.
    """
    layer_imgs = export_layers(
        image, depth_meters, layers=layers, feather_px=feather_px,
        object_assets=object_assets, ground_asset=ground_asset, sky_mask=sky_mask,
    )
    import base64
    import io

    out: dict[str, str] = {}
    for layer, img in layer_imgs.items():
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        out[layer] = f"data:image/{fmt.lower()};base64,{b64}"
    return out


def export_layers_to_disk(
    image: Image.Image,
    out_dir: Path,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
    name_prefix: str = "layer",
    object_assets: Optional[list] = None,
    ground_asset=None,
    sky_mask: Optional[np.ndarray] = None,
) -> dict[str, Path]:
    """Persist each layer PNG to ``out_dir`` and return their file paths."""
    layer_imgs = export_layers(
        image, depth_meters, layers=layers, feather_px=feather_px,
        object_assets=object_assets, ground_asset=ground_asset, sky_mask=sky_mask,
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for layer, img in layer_imgs.items():
        path = out_dir / f"{name_prefix}_{layer}.png"
        img.save(path, format="PNG")
        out[layer] = path
        logger.info("[layers] wrote %s (%d KB)", path, path.stat().st_size // 1024)
    return out


def build_z_offset_table() -> list[dict]:
    """Return the canonical Z-offset table for the 5 layers.

    The Blender plugin reads this exact table (via its manifest JSON) to know
    where to place each layer plane in 3D space.
    """
    table = []
    for layer in LAYER_ORDER:
        z_min, z_max = LAYER_Z_RANGES[layer]
        table.append({
            "layer": layer,
            "zOffset": LAYER_Z_OFFSETS[layer],
            "zMin": float(z_min),
            "zMax": float(z_max) if z_max != float("inf") else 9999.0,
        })
    return table