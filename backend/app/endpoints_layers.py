"""
Layer Export Endpoint — exposes `services.layer_exporter` via HTTP.

Phase 1 deliverable (Implementation Plan §1.1.2). Wired into `main.py` as a
new router. Accepts an image URL/base64 + optional depth map and returns 4
RGBA PNG data URIs (foreground/midground/background/sky) plus a Z-offset
table the Blender plugin can consume directly.

The endpoint is intentionally read-only / stateless so it can be called many
times without locking the GPU or holding memory: depth maps are produced by
the DepthAnything loader in the caller's pipeline and passed in here.

Phase 2 (2026-08-17) — Object-Aware Layers
-------------------------------------------
The endpoint optionally drives the full object + ground detection pipeline:

- ``autoAnchor`` (default True) — runs GroundingDINO + SAM2 over a scene-type
  specific prompt, returning one ``ObjectAsset`` per detection.
- ``reconstructGround`` (default True) — fits a RANSAC plane to detected
  ground region, returning a ``GroundAsset``.
- ``saveArchive=True`` + ``sceneId=...`` — persists all assets to
  ``backend/test_outputs/objects/<scene_id>/`` plus an
  ``objects_manifest.json``.

Backwards compatible: all new fields are optional and default to safe
values. Old clients keep working unchanged.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

from app.services.layer_exporter import (
    export_layers_to_data_uris,
    build_z_offset_table,
    LAYER_ORDER,
)
from app.services.object_assets import (
    make_object_summary,
    make_ground_summary,
    save_object_archive,
)
from app.utils.image_utils import load_image_from_url_or_base64

logger = logging.getLogger("aicss.layers")


router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────


class LayerExportRequest(BaseModel):
    imageUrl: str = Field(
        ...,
        description="Image URL (http/https), base64 data URL, or plain base64 string",
    )
    # We accept either an explicit depth map (preferred, lets the caller reuse
    # a depth they already computed) or layer-assignment objects — never both.
    depthMapUrl: Optional[str] = Field(
        default=None,
        description=(
            "Optional depth map URL/base64 (H×W grayscale). When provided, "
            "pixels are bucketed into layers via the depth ranges in "
            "`layer_exporter.LAYER_Z_RANGES`."
        ),
    )
    layers: Optional[list[str]] = Field(
        default=None,
        description=(
            "Optional subset of layer names to export. Defaults to all five: "
            "sky / background / midground / foreground / ground."
        ),
    )
    featherPx: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Edge feathering radius in pixels (0 = hard edges).",
    )

    # ── Phase 2: object-aware bucketing ────────────────────────────────────
    autoAnchor: bool = Field(
        default=True,
        description=(
            "When True, run GroundingDINO + SAM2 to produce per-object assets "
            "and merge them into the layer masks."
        ),
    )
    anchorPrompts: Optional[list[str]] = Field(
        default=None,
        description=(
            "Optional list of class names to override the scene-type "
            "fallback prompt (e.g. ['person','car','lamp'])."
        ),
    )
    sceneType: str = Field(
        default="outdoor",
        description=(
            "Scene category for selecting the default GroundingDINO prompt. "
            "One of 'outdoor', 'indoor', 'night', 'nature'."
        ),
    )
    reconstructGround: bool = Field(
        default=True,
        description=(
            "When True (and autoAnchor is True), fit a RANSAC ground plane "
            "to detected ground region and emit a dedicated ground layer."
        ),
    )
    intrinsics: Optional[list[float]] = Field(
        default=None,
        description=(
            "Optional 3×3 camera intrinsics matrix flattened to 9 floats "
            "(row-major). When omitted we use focal=1.2*max(w,h), "
            "principal point at the image centre."
        ),
    )
    saveArchive: bool = Field(
        default=False,
        description=(
            "When True, persist all assets to "
            "backend/test_outputs/objects/<sceneId>/."
        ),
    )
    sceneId: Optional[str] = Field(
        default=None,
        description="Required when saveArchive=True; names the archive directory.",
    )


class LayerDataUri(BaseModel):
    dataUri: str = Field(..., description="data:image/png;base64,... of the RGBA layer PNG")


class LayerZOffset(BaseModel):
    layer: str
    zOffset: float
    zMin: float
    zMax: float


class ObjectAssetSummary(BaseModel):
    object_id: str
    label: str
    score: float
    bbox: list[int]
    depth_mean: float
    depth_min: float
    depth_max: float
    layer_hint: str
    z_offset: float
    cutout_data_uri: str
    meta: dict


class GroundAssetSummary(BaseModel):
    object_id: str = "ground"
    plane: dict
    plane_normal: list[float]
    centroid: list[float]
    bbox: list[int]
    z_offset: float
    cutout_data_uri: str
    depth_correction_data_uri: str
    meta: dict


class LayerExportResponse(BaseModel):
    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")
    layers: dict[str, LayerDataUri] = Field(
        ...,
        description="Per-layer RGBA PNG data URIs keyed by layer name",
    )
    zOffsets: list[LayerZOffset] = Field(
        ...,
        description="Z-axis offset table for the Blender plugin",
    )
    objects: list[ObjectAssetSummary] = Field(
        default_factory=list,
        description="Per-object RGBA cutouts + metadata (Phase 2)",
    )
    ground: Optional[GroundAssetSummary] = Field(
        default=None,
        description="Reconstructed ground plane asset (Phase 2)",
    )
    layer_assignment: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map layer → list of object_ids in that layer (Phase 2)",
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _decode_depth_map(depth_b64_or_url: str, target_size: tuple[int, int]) -> np.ndarray:
    """Load a depth map (PNG grayscale) and resize to (h, w).

    Accepts data URLs, http(s) URLs, or plain base64. Returns float32 array in
    metres — we apply the same `depth_to_meters` scaling the rest of the
    codebase uses (×50 by default) so values line up with `settings.depth_buckets`.
    """
    from app.utils.image_utils import depth_to_meters

    img = load_image_from_url_or_base64(depth_b64_or_url, keep_alpha=False)
    if img.size != target_size:
        img = img.resize(target_size, Image.BILINEAR)
    depth_norm = np.array(img.convert("L"), dtype=np.float32) / 255.0
    return depth_to_meters(depth_norm)


def _validate_layers(requested: Optional[list[str]]) -> list[str]:
    """Validate the requested layer names against the canonical set."""
    if not requested:
        return list(LAYER_ORDER)
    out = []
    valid = set(LAYER_ORDER)
    for name in requested:
        n = name.strip().lower()
        if n not in valid:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown layer {name!r}. "
                    f"Valid layers: {sorted(valid)}"
                ),
            )
        if n not in out:
            out.append(n)
    return out


def _parse_intrinsics(values: Optional[list[float]]) -> Optional[np.ndarray]:
    if not values:
        return None
    if len(values) != 9:
        raise HTTPException(
            status_code=400,
            detail=f"intrinsics must have 9 floats (3x3 row-major); got {len(values)}",
        )
    arr = np.array(values, dtype=np.float64).reshape(3, 3)
    return arr


# ── Endpoint ───────────────────────────────────────────────────────────────────


@router.post(
    "/layers/export",
    response_model=LayerExportResponse,
    summary="Export depth-layer RGBA PNGs (+ per-object assets) from a scene image",
    description=(
        "Takes the original scene image (and optionally a depth map) and "
        "returns one RGBA PNG per depth layer (sky / background / midground / "
        "foreground / ground). Each PNG keeps the original RGB on its layer's "
        "pixels and is fully transparent elsewhere. With autoAnchor=True the "
        "endpoint also runs GroundingDINO + SAM2 to slice every detected "
        "object into its own RGBA cutout, and fits a RANSAC plane to the "
        "ground region. The response also includes the Z-axis offset table "
        "the Blender plugin reads to position the layers."
    ),
)
async def layers_export(req: LayerExportRequest) -> LayerExportResponse:
    # 1. Load the original image
    try:
        image = load_image_from_url_or_base64(req.imageUrl, keep_alpha=False)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to load imageUrl: {type(e).__name__}: {e}"[:500],
        )
    w, h = image.size

    # 2. Optionally load the depth map.
    depth_meters: Optional[np.ndarray] = None
    if req.depthMapUrl:
        try:
            depth_meters = _decode_depth_map(req.depthMapUrl, (w, h))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load depthMapUrl: {type(e).__name__}: {e}"[:500],
            )
    else:
        try:
            from app.models.model_manager import model_manager
            depth_meters = model_manager.depth_model.predict_meters(image, scale=50.0)
            logger.info(
                "[layers] auto-generated depth map via DepthAnything for %dx%d image",
                w, h,
            )
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Failed to auto-generate depth map: {type(e).__name__}: {e}"
                    " — supply `depthMapUrl` or ensure the depth model is downloaded."
                )[:500],
            )

    # 3. Validate layer subset
    selected = _validate_layers(req.layers)

    # 4. Phase 2: object detection + ground reconstruction
    object_assets = []
    ground_entries: list = []
    ground_asset = None
    intrinsics = _parse_intrinsics(req.intrinsics)

    if req.autoAnchor:
        try:
            from app.services.object_detector import detect_objects
            object_assets, ground_entries = detect_objects(
                image,
                depth_meters,
                prompt=req.anchorPrompts,
                scene_type=req.sceneType,
            )
        except Exception as e:
            import traceback
            logger.warning(
                "[layers] object detection failed: %s\n%s",
                e, traceback.format_exc(),
            )

    if req.reconstructGround:
        try:
            from app.services.ground_reconstructor import reconstruct_ground
            ground_asset = reconstruct_ground(
                image,
                depth_meters,
                detections=ground_entries,
                intrinsics=intrinsics,
            )
        except Exception as e:
            logger.warning("[layers] ground reconstruction failed: %s — skipping", e)

    # 5. Export layers → data URIs
    layer_uris = export_layers_to_data_uris(
        image,
        depth_meters,
        layers=selected,
        feather_px=req.featherPx,
        object_assets=object_assets,
        ground_asset=ground_asset,
    )

    # 6. Persist archive when requested
    archive_manifest = None
    if req.saveArchive:
        if not req.sceneId:
            raise HTTPException(
                status_code=400,
                detail="saveArchive=True requires sceneId to be set.",
            )
        try:
            # Anchor the archive directory to BASE_DIR (the ``backend/``
            # root) so we don't end up with nested ``backend/backend/…``
            # paths when the caller invokes the endpoint via uvicorn from
            # an unexpected working directory.
            from app.config import BASE_DIR
            archive_root = BASE_DIR / "test_outputs" / "objects"
            archive_manifest = save_object_archive(
                scene_id=req.sceneId,
                objects=object_assets,
                ground=ground_asset,
                archive_root=archive_root,
                image_url=req.imageUrl,
            )
            logger.info(
                "[layers] wrote archive for scene_id=%s (%d objects, ground=%s) → %s",
                req.sceneId, len(object_assets), ground_asset is not None, archive_root / req.sceneId,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save archive: {type(e).__name__}: {e}"[:500],
            )

    # 7. Build the response (Pydantic models — frontend gets a stable schema)
    obj_summaries = [
        ObjectAssetSummary(**make_object_summary(o)) for o in object_assets
    ]
    ground_summary_payload = make_ground_summary(ground_asset)
    ground_summary = (
        GroundAssetSummary(**ground_summary_payload) if ground_summary_payload else None
    )
    layer_assignment: dict[str, list[str]] = {}
    for o in object_assets:
        layer_assignment.setdefault(o.layer_hint, []).append(o.object_id)
    if ground_asset is not None:
        layer_assignment.setdefault("ground", []).append(ground_asset.object_id)

    return LayerExportResponse(
        width=w,
        height=h,
        layers={name: LayerDataUri(dataUri=uri) for name, uri in layer_uris.items()},
        zOffsets=[LayerZOffset(**row) for row in build_z_offset_table()],
        objects=obj_summaries,
        ground=ground_summary,
        layer_assignment=layer_assignment,
    )