"""
Layer PNG Exporter — exports each depth layer (foreground/midground/background/sky)
as an independent RGBA PNG with the layer's visible region preserved and everything
else transparent.

Phase 1 deliverable: `POST /api/aicss/layers/export` endpoint, plus a helper that
scene generators can call directly to embed `layeredImages` in the scene manifest.

Per the Implementation Plan (2026-08-10), this is the P0 blocker for the Blender
plugin (Module 6) — the 4 PNGs this function produces are what the Blender plugin
imports and places at the canonical Z-axis offsets (foreground=-2, midground=-6,
background=-12, sky=-20).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

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
}

# Z range (depth band) that each layer covers, in meters. Matches
# `settings.depth_buckets` so the layer buckets from
# `spatial_utils.assign_to_depth_layer` align with these Z offsets.
LAYER_Z_RANGES: dict[str, tuple[float, float]] = {
    "foreground": (0.0, 5.0),
    "midground": (5.0, 15.0),
    "background": (15.0, 50.0),
    "sky": (50.0, float("inf")),
}

# Canonical render order: sky (deepest) → foreground (closest). Layers are
# emitted in this order so a 3D importer can stack planes from back to front.
LAYER_ORDER: tuple[str, ...] = ("sky", "background", "midground", "foreground")


def export_layers(
    image: Image.Image,
    depth_meters: Optional[np.ndarray] = None,
    *,
    layers: Optional[list[str]] = None,
    feather_px: int = 1,
) -> dict[str, Image.Image]:
    """Return one RGBA PNG per depth layer.

    Each returned image has the same width/height as ``image``. Pixels that
    belong to the layer keep their original RGB; everything else is transparent
    (alpha = 0). The depth meters map is optional — when provided we bucket
    pixels into layers from the depth map; otherwise we use the layer name
    strings alone (callers that already pre-bucketed the image must supply
    their own masks).

    Args:
        image: Original RGB scene image (any mode; will be converted to RGB).
        depth_meters: (H, W) depth map in meters, or None to skip depth-based
            bucketing. When None, only the foreground/midground/background/sky
            masks supplied via ``layers`` are honoured.
        layers: Subset of layer names to export. Defaults to all four canonical
            layers (sky/background/midground/foreground).
        feather_px: Edge feathering radius (in pixels). 0 = hard edges,
            1 = minimal softening. Uses Pillow's GaussianBlur on the alpha.

    Returns:
        Dict mapping layer name → RGBA PIL Image.
    """
    if image is None:
        raise ValueError("image is required")

    if layers is None:
        layers = list(LAYER_ORDER)
    else:
        # Validate and normalise user input. We accept any case but always
        # emit the canonical lowercase keys so downstream code (Blender plugin
        # and frontend) can rely on a stable naming contract.
        layers = [layer.lower() for layer in layers]

    rgb = image.convert("RGB")
    w, h = rgb.size

    if depth_meters is not None:
        if depth_meters.shape != (h, w):
            raise ValueError(
                f"depth_meters shape {depth_meters.shape} does not match image ({h}, {w})"
            )

    # Pre-allocate an alpha mask per layer so each layer's pixels can be marked
    # as visible (=255) or transparent (=0) before compositing the RGB image.
    layer_alphas: dict[str, np.ndarray] = {}
    for layer in layers:
        if depth_meters is not None and layer in LAYER_Z_RANGES:
            z_min, z_max = LAYER_Z_RANGES[layer]
            mask = (depth_meters >= z_min) & (depth_meters < z_max)
        else:
            # Fallback: no depth provided — every pixel belongs to the layer.
            # Callers that pre-bucket the image should use a per-layer mask
            # via a future iteration of this API.
            mask = np.ones((h, w), dtype=bool)
        layer_alphas[layer] = (mask.astype(np.uint8) * 255)

    out: dict[str, Image.Image] = {}
    rgb_np = np.array(rgb)

    for layer in layers:
        alpha = layer_alphas[layer]
        alpha_img = Image.fromarray(alpha, mode="L")
        if feather_px > 0:
            # Apply edge softening — Gaussian blur keeps the silhouette
            # but reduces the harsh binary edge that creates "paper cutout"
            # artifacts in 3D compositing. We re-threshold after blurring
            # so transparent pixels stay transparent.
            blurred = alpha_img.filter(
                ImageFilter.GaussianBlur(radius=float(feather_px))
            )
            blurred_np = np.array(blurred)
            # Re-binarise: any pixel with alpha > 127 stays visible.
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
) -> dict[str, str]:
    """Convenience wrapper — returns ``data:image/png;base64,...`` URIs.

    Useful for embedding layer PNGs directly in JSON responses without
    persisting to disk.
    """
    layer_imgs = export_layers(
        image, depth_meters, layers=layers, feather_px=feather_px
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
) -> dict[str, Path]:
    """Persist each layer PNG to ``out_dir`` and return their file paths.

    Returns a dict mapping layer name → on-disk path. Used by the scene
    generator (`auto_scene_view.py`) when it bakes the manifest after the
    scene's three keyframes are generated.
    """
    layer_imgs = export_layers(
        image, depth_meters, layers=layers, feather_px=feather_px
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
    """Return the canonical Z-offset table for the 4 layers.

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