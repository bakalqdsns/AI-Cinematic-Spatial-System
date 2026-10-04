"""
Object detector — wraps GroundingDINO + SAM2 to produce ``ObjectAsset`` rows.

The pipeline is:

1. Run GroundingDINO with a (possibly scene-type-specific) text prompt to get
   ``Detection(box, label, score)`` triples.
2. Pass the boxes to SAM2 for precise instance masks.
3. For each surviving detection:
     - Resolve ``layer_hint`` from ``settings.layer_hint_rules``.
     - Compute depth stats over the mask (``mean / min / max``).
     - Build the transparent RGBA cutout.
     - Pack into ``ObjectAsset``.

If the user supplies a custom ``anchor_prompts`` list we use it directly; otherwise
we pick the right ``vlm_fallback_prompts[scene_type]`` from settings. To keep
the ground plane separate from a generic detection pass, we add a small suffix
to the prompt that includes ground-class nouns; ``reconstruct_ground`` will use
the same boxes / masks.

We deliberately do **not** unload GroundingDINO / SAM2 here — the caller is
responsible for that, just like the rest of the codebase does after
``/analyze`` runs.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PIL import Image

from app.config import settings
from app.services.object_assets import (
    ObjectAsset,
    bbox_of_mask,
    make_object_rgba,
    rgba_to_data_uri,
)

logger = logging.getLogger("aicss.object_detector")


# Default scene-type → dot-separated classes. Mirrors
# ``settings.vlm_fallback_prompts`` but kept here so we don't pull settings at
# import time (avoid circular imports in tests).
DEFAULT_PROMPTS: dict[str, str] = {
    "outdoor": "person.car.truck.lamp.sign.tree.building.bicycle.motorcycle.dog.mountain.fence",
    "indoor":  "person.chair.table.sofa.bed.lamp.door.window.curtain",
    "night":   "person.car.building.light.sign.window.lamp.tree.road",
    "nature":  "animal.rock.tree.flower.bird.mountain.water.grass",
}

# Ground-class nouns appended to the detection prompt. Kept as a constant so
# the caller (or ``ground_reconstructor``) can intersect the detection set.
GROUND_CLASSES: tuple[str, ...] = (
    "ground", "road", "floor", "sidewalk", "grass", "sand", "water", "snow",
)


def resolve_prompt(
    scene_type: str = "outdoor",
    custom: Optional[list[str]] = None,
) -> str:
    """Pick the GroundingDINO prompt — custom → fallback prompt → default.

    We always append ``GROUND_CLASSES`` so the ground reconstruction pass can
    reuse the same detection boxes without a second GroundingDINO call.
    """
    if custom:
        base = " . ".join(custom) + " ."
    else:
        raw = settings.vlm_fallback_prompts.get(scene_type) or DEFAULT_PROMPTS.get(
            scene_type, DEFAULT_PROMPTS["outdoor"]
        )
        # The settings version uses dot separators — Grounding DINO accepts both
        # "." and " . " so we normalise on " . " (the format expected by the
        # processor's post-processing).
        base = " . ".join(s for s in raw.split(".") if s.strip()) + " ."
    # Append ground nouns so the same detection pass covers the ground mask.
    suffix = " . ".join(GROUND_CLASSES)
    return f"{base} {suffix}"


def detect_objects(
    image: Image.Image,
    depth_meters: Optional[np.ndarray],
    *,
    prompt: Optional[list[str]] = None,
    scene_type: str = "outdoor",
    confidence_threshold: float = 0.3,
    max_objects: int = 32,
    min_mask_area_px: int = 256,
    layer_z_offsets: Optional[dict[str, float]] = None,
) -> tuple[list[ObjectAsset], list[tuple[object, np.ndarray]]]:
    """Run GroundingDINO + SAM2, return (object_assets, raw_ground_class_entries).

    Returns:
        object_assets: per-detection ``ObjectAsset`` rows ready for archive /
            response embedding.
        raw_ground_class_entries: tuples ``(detection, sam2_mask)`` for the
            classes that look like ground — fed to ``ground_reconstructor``.
    """
    from app.models.model_manager import model_manager  # lazy import

    rgb = image.convert("RGB")
    w, h = rgb.size

    text_prompt = resolve_prompt(scene_type=scene_type, custom=prompt)
    logger.info("[object_detector] GroundingDINO prompt: %s", text_prompt)

    detections = model_manager.grounding_dino.detect(
        rgb, prompt=text_prompt, threshold=confidence_threshold
    )
    if not detections:
        logger.info("[object_detector] no detections for prompt=%s", text_prompt)
        return [], []

    # Sort by score (high→low) and cap to max_objects.
    detections.sort(key=lambda d: d.score, reverse=True)
    detections = detections[:max_objects]

    # Build the box matrix for SAM2 in one shot.
    boxes = np.stack([d.box for d in detections]).astype(np.float32)
    scores_arr = np.array([d.score for d in detections], dtype=np.float32)
    masks_with_score = model_manager.sam2.predict_masks_from_boxes(
        rgb, boxes, scores=scores_arr
    )

    # ── Edge refinement ─────────────────────────────────────────────────────────
    # SAM2 masks are pixel-aligned and look hard against a textured background.
    # Snap each mask's contour to nearby Canny edges so the resulting cutout
    # follows the true subject boundary; combined with the Gaussian blur in
    # ``make_object_rgba`` this gives a soft, anti-aliased silhouette.
    try:
        from app.models.sam2_loader import refine_mask_edges
        image_np = np.array(rgb)
        masks_with_score = refine_mask_edges(
            masks_with_score, image_np, snap_distance=8,
        )
    except Exception as e:
        logger.warning(
            "[object_detector] refine_mask_edges failed, falling back to "
            "raw SAM2 masks: %s", e,
        )

    # Resolve layer hint from settings (fall back to "foreground" for unknown labels).
    hint_rules = settings.layer_hint_rules

    out: list[ObjectAsset] = []
    ground_entries: list[tuple[object, np.ndarray]] = []

    for det, (mask, sam_score) in zip(detections, masks_with_score):
        # Drop tiny masks — these are usually false positives.
        if mask.sum() < min_mask_area_px:
            continue
        # Clip mask to image bounds (SAM2 may extend slightly).
        mask_clipped = mask[:h, :w] if mask.shape != (h, w) else mask
        bbox = bbox_of_mask(mask_clipped)

        label = det.label.lower().strip()
        layer_hint = hint_rules.get(label, "foreground")

        # Depth stats over the mask (None when depth_meters was not provided).
        if depth_meters is not None and depth_meters.shape == (h, w):
            d_in = depth_meters[mask_clipped]
            if d_in.size:
                depth_mean = float(d_in.mean())
                depth_min = float(d_in.min())
                depth_max = float(d_in.max())
            else:
                depth_mean = depth_min = depth_max = 0.0
        else:
            depth_mean = depth_min = depth_max = 0.0

        rgba = make_object_rgba(rgb, mask_clipped)
        cutout_data_uri = rgba_to_data_uri(rgba)

        # Z offset comes from the layer hint (caller can override via layer_z_offsets).
        z_table = layer_z_offsets or {}
        z_offset = float(z_table.get(layer_hint, _default_z(layer_hint)))

        area_px = int(mask_clipped.sum())
        vertical_pos = float(((bbox[1] + bbox[3]) / 2.0) / h) if h else 0.0
        meta = {
            "area_px": area_px,
            "vertical_pos": vertical_pos,
            "sam_score": float(sam_score),
            "aspect": float((bbox[2] - bbox[0]) / max(1, bbox[3] - bbox[1])),
        }

        asset = ObjectAsset(
            object_id=det.object_id,
            label=label,
            score=float(det.score),
            bbox=bbox,
            mask=mask_clipped,
            depth_mean=depth_mean,
            depth_min=depth_min,
            depth_max=depth_max,
            layer_hint=layer_hint,
            z_offset=z_offset,
            rgba=rgba,
            cutout_data_uri=cutout_data_uri,
            meta=meta,
        )
        out.append(asset)

        if layer_hint == "ground":
            ground_entries.append((det, mask_clipped))

    logger.info(
        "[object_detector] %d objects (%d foreground, %d midground, %d background, %d ground)",
        len(out),
        sum(1 for o in out if o.layer_hint == "foreground"),
        sum(1 for o in out if o.layer_hint == "midground"),
        sum(1 for o in out if o.layer_hint == "background"),
        sum(1 for o in out if o.layer_hint == "ground"),
    )

    return out, ground_entries


def _default_z(layer_hint: str) -> float:
    """Fallback Z offsets when the caller didn't pass a custom table."""
    return {
        "foreground": -2.0,
        "midground": -6.0,
        "background": -12.0,
        "ground": -1.5,
    }.get(layer_hint, -2.0)