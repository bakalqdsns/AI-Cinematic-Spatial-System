"""
Object / Ground asset dataclasses and archive helpers.

This module defines the on-disk and in-memory representation of two kinds of
"first-class" assets the layer pipeline now produces per scene:

1. ``ObjectAsset`` — one row per GroundingDINO+SAM2 detection. Each becomes its
   own transparent-background RGBA PNG + JSON sidecar, and is independently
   consumable by the Blender plugin as a separate mesh / sprite.

2. ``GroundAsset`` — a 3D plane fit (RANSAC) of the detected ground region,
   plus a depth-corrected RGBA that maps the original pixels onto the fitted
   plane. Exposed as ``ground.png`` + ``ground_corrected_depth.png``.

Both kinds write to ``backend/test_outputs/objects/<scene_id>/`` (overridable
via ``archive_root``) and register themselves in ``objects_manifest.json`` —
this manifest is the single source of truth the Blender plugin reads.

落盘约定:
- 单个物体文件: ``obj_<index:04d>_<label>.png`` / ``.json``
- ground: ``ground.png`` / ``ground_corrected_depth.png`` / ``ground.json``
- 索引: ``objects_manifest.json``

Dependencies: numpy, Pillow. Pure data — no model imports here.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger("aicss.object_assets")


# ──────────────────────────────────────────────────────────────────────────────
# ObjectAsset
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ObjectAsset:
    """One detected object — its bounding box, mask, depth stats, and cutout.

    The ``rgba`` field is the source-of-truth image (RGB + mask as alpha);
    ``cutout_data_uri`` is the same image, base64-encoded for embedding into
    JSON responses (so the frontend can preview the cutout without a second
    HTTP round-trip).
    """

    object_id: str                          # "obj_0001_person"
    label: str                              # "person"
    score: float                            # GroundingDINO confidence
    bbox: tuple[int, int, int, int]         # (x1, y1, x2, y2) in pixels
    mask: np.ndarray                        # H×W bool
    depth_mean: float                       # mean depth in mask (m)
    depth_min: float
    depth_max: float
    layer_hint: str                         # "foreground" / "midground" / "background"
    z_offset: float                         # layer-hint-derived Z offset
    rgba: Image.Image                       # transparent-background RGBA
    cutout_data_uri: str = ""               # data:image/png;base64,... of rgba
    meta: dict = field(default_factory=dict)  # area_px / aspect / vertical_pos


# ──────────────────────────────────────────────────────────────────────────────
# GroundAsset
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class GroundAsset:
    """3D-plane fit of the ground region, with depth-corrected RGBA."""

    object_id: str = "ground"
    plane: dict = field(default_factory=dict)            # {"a","b","c","d"} for ax+by+cz+d=0
    plane_normal: list[float] = field(default_factory=list)  # 归一化法向量 (a,b,c)
    centroid: list[float] = field(default_factory=list)      # 地面点云中心 (x,y,z)
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)        # tight bbox of ground mask
    cutout: Optional[Image.Image] = None                 # RGBA, ground pixels visible
    depth_correction: Optional[np.ndarray] = None        # H×W float32 (only inside mask)
    z_offset: float = -1.5                               # ground plane Z offset
    meta: dict = field(default_factory=dict)             # inlier_ratio / vertical_pos / area_px

    def depth_correction_data_uri(self) -> str:
        """Encode ``depth_correction`` as a grayscale PNG data URI for JSON embedding.

        Depth is normalised to (0, 255) by min/max over the mask before encoding
        so that the plane depth is human-inspectable from the PNG alone. Outside
        the mask the value is 0 (transparent in viewer terms).
        """
        if self.depth_correction is None:
            return ""
        d = self.depth_correction
        valid = d > 0
        if not np.any(valid):
            return ""
        dmin = float(d[valid].min())
        dmax = float(d[valid].max())
        if dmax - dmin < 1e-6:
            dmax = dmin + 1.0
        encoded = np.zeros_like(d, dtype=np.uint8)
        encoded[valid] = ((d[valid] - dmin) / (dmax - dmin) * 255.0).astype(np.uint8)
        # Pack into a grayscale PNG, single-channel.
        img = Image.fromarray(encoded, mode="L")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def rgba_to_data_uri(rgba: Image.Image, fmt: str = "PNG") -> str:
    """Encode a PIL Image as a ``data:image/png;base64,...`` URI."""
    buf = io.BytesIO()
    rgba.save(buf, format=fmt)
    return f"data:image/{fmt.lower()};base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"


def make_object_rgba(image: Image.Image, mask: np.ndarray, *, feather_px: int = 1) -> Image.Image:
    """Take an RGB image + bool mask and produce a transparent-background RGBA.

    Pixels outside the mask get alpha=0; pixels inside keep their RGB. This
    is the canonical "cutout" the Blender plugin imports as a plane texture.

    Edge feathering:
        SAM2 masks are pixel-aligned with the underlying subject and look hard
        when composited onto a textured background.  We apply a tiny Gaussian
        blur to the alpha channel (default radius 1 px) to soften the boundary
        by ~1 pixel on each side.  The blurred alpha is then re-binarised at
        50% so the silhouette area stays the same — only the silhouette edge
        becomes antialiased.

    Args:
        image: RGB image, any size.
        mask: H×W bool ndarray, True = subject.
        feather_px: Edge feathering radius.  0 disables feathering (raw 0/255).
    """
    rgb = np.array(image.convert("RGB"))
    alpha_u8 = (mask.astype(np.uint8) * 255)

    if feather_px and feather_px > 0:
        # PIL GaussianBlur gives a real soft ramp — passing the alpha straight
        # through (instead of re-binarising) keeps the gradient, which is what
        # the Blender HASHED alpha-blend mode needs to anti-alias the silhouette.
        from PIL import ImageFilter
        alpha_img = Image.fromarray(alpha_u8, mode="L").filter(
            ImageFilter.GaussianBlur(radius=float(feather_px))
        )
        alpha_u8 = np.array(alpha_img)

    rgba_arr = np.dstack([rgb, alpha_u8])
    return Image.fromarray(rgba_arr, mode="RGBA")


def bbox_of_mask(mask: np.ndarray) -> tuple[int, int, int, int]:
    """Return (x1, y1, x2, y2) tight bbox of a bool mask, or (0,0,0,0) if empty."""
    if not mask.any():
        return (0, 0, 0, 0)
    ys, xs = np.where(mask)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


# ──────────────────────────────────────────────────────────────────────────────
# Archive persistence
# ──────────────────────────────────────────────────────────────────────────────


def save_object_archive(
    scene_id: str,
    objects: list[ObjectAsset],
    ground: Optional[GroundAsset] = None,
    archive_root: Path = Path("backend/test_outputs/objects"),
    image_url: Optional[str] = None,
) -> dict:
    """Persist objects + ground to ``archive_root/<scene_id>/`` and return the manifest.

    Returns the manifest dict (also written to ``objects_manifest.json``). The
    Blender plugin can read the manifest to enumerate all independent assets
    without parsing the layer PNGs.
    """
    out_dir = Path(archive_root) / scene_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Per-object files
    obj_entries: list[dict] = []
    for i, obj in enumerate(objects):
        slug = obj.label.replace(" ", "_")
        fname = f"obj_{i:04d}_{slug}"
        png_path = out_dir / f"{fname}.png"
        json_path = out_dir / f"{fname}.json"
        obj.rgba.save(png_path, format="PNG")
        meta = {
            "object_id": obj.object_id,
            "label": obj.label,
            "score": float(obj.score),
            "bbox": [int(v) for v in obj.bbox],
            "depth_mean": float(obj.depth_mean),
            "depth_min": float(obj.depth_min),
            "depth_max": float(obj.depth_max),
            "layer_hint": obj.layer_hint,
            "z_offset": float(obj.z_offset),
            "cutout": f"{fname}.png",
            "meta": obj.meta,
        }
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        obj_entries.append(meta)
        logger.info("[object_assets] wrote %s (%d KB)", png_path, png_path.stat().st_size // 1024)

    # 2. Ground files
    ground_entry: Optional[dict] = None
    if ground is not None:
        if ground.cutout is not None:
            ground_png = out_dir / "ground.png"
            ground.cutout.save(ground_png, format="PNG")
        if ground.depth_correction is not None:
            # Persist as a 16-bit grayscale PNG (depth precision matters).
            d = ground.depth_correction
            valid = d > 0
            if valid.any():
                dmin = float(d[valid].min())
                dmax = float(d[valid].max())
                if dmax - dmin < 1e-6:
                    dmax = dmin + 1.0
                norm = np.zeros_like(d, dtype=np.float32)
                norm[valid] = (d[valid] - dmin) / (dmax - dmin)
            else:
                norm = np.zeros_like(d, dtype=np.float32)
            depth_png = out_dir / "ground_corrected_depth.png"
            Image.fromarray((norm * 65535.0).astype(np.uint16), mode="I;16").save(
                depth_png, format="PNG"
            )
        ground_entry = {
            "object_id": ground.object_id,
            "plane": ground.plane,
            "plane_normal": ground.plane_normal,
            "centroid": ground.centroid,
            "bbox": [int(v) for v in ground.bbox],
            "z_offset": float(ground.z_offset),
            "cutout": "ground.png" if ground.cutout is not None else None,
            "depth_correction": "ground_corrected_depth.png" if ground.depth_correction is not None else None,
            "meta": ground.meta,
        }
        ground_json_path = out_dir / "ground.json"
        with ground_json_path.open("w", encoding="utf-8") as f:
            json.dump(ground_entry, f, ensure_ascii=False, indent=2)
        logger.info("[object_assets] wrote ground.json + ground.png for scene_id=%s", scene_id)

    # 3. Manifest
    manifest = {
        "scene_id": scene_id,
        "imageUrl": image_url,
        "objects": obj_entries,
        "ground": ground_entry,
    }
    manifest_path = out_dir / "objects_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest


def make_object_summary(obj: ObjectAsset) -> dict:
    """Compact JSON-serialisable summary of an ``ObjectAsset`` for the API response."""
    return {
        "object_id": obj.object_id,
        "label": obj.label,
        "score": float(obj.score),
        "bbox": [int(v) for v in obj.bbox],
        "depth_mean": float(obj.depth_mean),
        "depth_min": float(obj.depth_min),
        "depth_max": float(obj.depth_max),
        "layer_hint": obj.layer_hint,
        "z_offset": float(obj.z_offset),
        "cutout_data_uri": obj.cutout_data_uri,
        "meta": obj.meta,
    }


def make_ground_summary(ground: Optional[GroundAsset]) -> Optional[dict]:
    """Compact JSON-serialisable summary of a ``GroundAsset`` (or None)."""
    if ground is None:
        return None
    cutout_uri = rgba_to_data_uri(ground.cutout) if ground.cutout is not None else ""
    return {
        "object_id": ground.object_id,
        "plane": ground.plane,
        "plane_normal": list(ground.plane_normal),
        "centroid": list(ground.centroid),
        "bbox": [int(v) for v in ground.bbox],
        "z_offset": float(ground.z_offset),
        "cutout_data_uri": cutout_uri,
        "depth_correction_data_uri": ground.depth_correction_data_uri(),
        "meta": ground.meta,
    }