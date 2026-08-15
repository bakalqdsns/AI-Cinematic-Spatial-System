"""
Layer Export Endpoint — exposes `services.layer_exporter` via HTTP.

Phase 1 deliverable (Implementation Plan §1.1.2). Wired into `main.py` as a
new router. Accepts an image URL/base64 + optional depth map and returns 4
RGBA PNG data URIs (foreground/midground/background/sky) plus a Z-offset
table the Blender plugin can consume directly.

The endpoint is intentionally read-only / stateless so it can be called many
times without locking the GPU or holding memory: depth maps are produced by
the DepthAnything loader in the caller's pipeline and passed in here.
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
            "Optional subset of layer names to export. Defaults to all four: "
            "sky / background / midground / foreground."
        ),
    )
    featherPx: int = Field(
        default=1,
        ge=0,
        le=10,
        description="Edge feathering radius in pixels (0 = hard edges).",
    )


class LayerDataUri(BaseModel):
    dataUri: str = Field(..., description="data:image/png;base64,... of the RGBA layer PNG")


class LayerZOffset(BaseModel):
    layer: str
    zOffset: float
    zMin: float
    zMax: float


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


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/layers/export",
    response_model=LayerExportResponse,
    summary="Export 4 depth-layer RGBA PNGs from a scene image",
    description=(
        "Takes the original scene image (and optionally a depth map) and "
        "returns one RGBA PNG per depth layer (sky / background / midground / "
        "foreground). Each PNG keeps the original RGB on its layer's pixels "
        "and is fully transparent elsewhere. The response also includes the "
        "Z-axis offset table the Blender plugin reads to position the layers."
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

    # 2. Optionally load the depth map
    depth_meters: Optional[np.ndarray] = None
    if req.depthMapUrl:
        try:
            depth_meters = _decode_depth_map(req.depthMapUrl, (w, h))
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load depthMapUrl: {type(e).__name__}: {e}"[:500],
            )

    # 3. Validate layer subset
    selected = _validate_layers(req.layers)

    # 4. Export layers → data URIs
    layer_uris = export_layers_to_data_uris(
        image,
        depth_meters,
        layers=selected,
        feather_px=req.featherPx,
    )

    # 5. Build the response (Pydantic models — frontend gets a stable schema)
    return LayerExportResponse(
        width=w,
        height=h,
        layers={name: LayerDataUri(dataUri=uri) for name, uri in layer_uris.items()},
        zOffsets=[LayerZOffset(**row) for row in build_z_offset_table()],
    )