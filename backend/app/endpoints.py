"""
AICSS API Endpoints.

All endpoints for the AICSS inference pipeline:
  POST /api/aicss/analyze       — Full pipeline (depth + segment + layers + graph)
  GET  /api/aicss/mask/{id}     — Serve a single object mask PNG on-demand
  POST /api/aicss/depth         — Depth map only
  POST /api/aicss/segment       — Object segmentation only
  POST /api/aicss/layers        — Build spatial layers
  POST /api/aicss/scene-graph   — Build scene graph
  POST /api/aicss/billboard     — Generate RGBA billboard texture
  POST /api/aicss/multiface     — Generate 6-face pseudo-3D textures
"""
# ─── LRU mask store ──────────────────────────────────────────────────────────
# Stores object_id -> base64 PNG, capped at _MAX_STORED.
# Oldest entries are evicted when capacity is exceeded.
from collections import OrderedDict

_MASK_STORE: OrderedDict[str, str] = OrderedDict()
_MAX_STORED = 200


def _store_mask(object_id: str, data_url: str) -> None:
    if object_id in _MASK_STORE:
        _MASK_STORE.move_to_end(object_id)
    _MASK_STORE[object_id] = data_url
    while len(_MASK_STORE) > _MAX_STORED:
        _MASK_STORE.popitem(last=False)


# ─── URL validation ─────────────────────────────────────────────────────────
_ALLOWED_IMAGE_SCHEMES = frozenset({"http", "https", "data"})


def _validate_image_url(url: str) -> None:
    """Raise ValueError if url is not a safe image source."""
    if url.startswith("data:"):
        return  # base64 data URI is always safe
    if url.startswith("//"):
        raise ValueError("Protocol-relative URLs are not allowed.")
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_IMAGE_SCHEMES:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed. Use http, https, or base64.")


# ─────────────────────────────────────────────────────────────────────────────
# Imports
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import base64
import io
import sys
import time
import traceback
import uuid
import logging
from typing import Optional

import httpx
import torch
import numpy as np
import cv2

_log = logging.getLogger("aicss")
from PIL import Image
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.config import settings, DEVICE
from app.models.model_manager import model_manager
from app.utils.image_utils import (
    load_image_from_url_or_base64,
    pil_to_base64,
    base64_to_pil,
    numpy_to_pil_depth,
    depth_to_meters,
    bbox_to_xywh,
    estimate_depth_from_bbox,
    rotate_image_90,
    flip_image,
)
from app.utils.spatial_utils import (
    assign_to_depth_layer,
    build_spatial_layers_from_objects,
    build_scene_graph_from_objects,
)
from app.models.sam2_loader import refine_mask_edges, extract_polygon_from_mask
from app.utils.inpaint_utils import generate_inpaint
from app.utils.vlm_utils import vlm_detect
from app.models.auto_prompt import get_auto_prompt, infer_scene_from_image
from app.models.depth_layer import compute_depth_layer_bounds, assign_mask_to_layer
from app.utils.nms_utils import nms_masks, filter_small_masks
from app.utils.image_utils import pil_to_file

# ─────────────────────────────────────────────────────────────────────────────
# Constants for AutoMask filtering
# ─────────────────────────────────────────────────────────────────────────────

MIN_AREA_RATIO = 0.002   # AutoMask area / image area must exceed this threshold
MAX_AUTOMASKS = 100      # Keep only the top-N largest AutoMasks by area
AUTO_IOU_THRESHOLD = 0.6  # AutoMask IoU > this with DINO result → discarded


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class ImageUrlRequest(BaseModel):
    imageUrl: str = Field(..., description="Image URL or base64 data URL")
    shotId: Optional[str] = Field(None, description="Optional shot ID for tracking")


class AnalyzeRequest(BaseModel):
    imageUrl: str
    shotId: str
    apiKey: Optional[str] = Field(None, description="DashScope API key — optional; if not provided, uses automatic scene detection")


class DepthRequest(BaseModel):
    imageUrl: str


class SegmentRequest(BaseModel):
    imageUrl: str
    apiKey: Optional[str] = Field(None, description="DashScope API key — optional")


class LayersRequest(BaseModel):
    depthMap: str = Field(..., description="Base64-encoded depth PNG")
    objects: list[dict] = Field(..., description="List of SpatialObject dicts")
    imageWidth: int = Field(1024)
    imageHeight: int = Field(768)


class SceneGraphRequest(BaseModel):
    shotId: str
    objects: list[dict]


class BillboardRequest(BaseModel):
    imageUrl: str
    objectId: str
    boundingBox: dict = Field(..., description="{x, y, w, h} normalized 0-1")
    polygon: list[list[float]] = Field(default_factory=list, description="[[x,y],...] normalized 0-1, overrides boundingBox for precise cropping")


class MultifaceRequest(BaseModel):
    imageUrl: str
    objectId: str
    boundingBox: dict = Field(..., description="{x, y, w, h} normalized 0-1")
    polygon: list[list[float]] = Field(default_factory=list, description="[[x,y],...] normalized 0-1, overrides boundingBox for precise cropping")


class InpaintRequest(BaseModel):
    imageUrl: str = Field(..., description="Cropped image, base64 or URL")
    maskDataUrl: str = Field(..., description="Inverse mask (RGBA), white=edit area, black=keep area")
    prompt: str = Field(..., description="Inpainting prompt")
    apiKey: Optional[str] = Field(None, description="DashScope API key — falls back to AICSS_DASHSCOPE_API_KEY env var if not provided")


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: load image
# ─────────────────────────────────────────────────────────────────────────────

async def _load_image(url: str) -> Image.Image:
    """Load image from URL or base64. Validates URL scheme before fetching."""
    _validate_image_url(url)
    return load_image_from_url_or_base64(url)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/analyze — Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """
    Full AICSS analysis pipeline (fully local — no API key required).

    1. Load image
    2. Run DepthAnything V2 → depth map (async with DINO)
    3. Run Grounding DINO + SAM2 → object masks (async with depth)
       - If apiKey provided: VLM-enhanced class list
       - Otherwise: automatic scene-specific prompt
    4. Run SAM2 automatic masks → fill coverage gaps
    5. Merge all detections, apply NMS
    6. Build spatial layers
    7. Build scene graph
    8. Return all results
    """
    analysis_id = f"aicss_{uuid.uuid4().hex[:8]}"
    _log.info(f"[{analysis_id}] === Pipeline start ===")

    def _t():
        return time.perf_counter()

    timings: dict[str, float] = {}
    t_last = _t()

    try:
        # Step 1: Load image
        image = await _load_image(request.imageUrl)
        w, h = image.size
        timings["1_image_load"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 1_image_load: {timings['1_image_load']*1000:.0f}ms  ({w}x{h})")

        # Step 2: Depth estimation
        depth_norm = model_manager.depth_model.predict(image)
        depth_m = depth_to_meters(depth_norm, scale=50.0)
        timings["2_depth_model"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 2_depth_model: {timings['2_depth_model']*1000:.0f}ms")

        # Convert depth to PNG file for frontend
        depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
        depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)
        depth_url = pil_to_file(depth_pil_resized, f"depth_{analysis_id}.png")
        timings["3_depth_save"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 3_depth_save: {timings['3_depth_save']*1000:.0f}ms")

        # Step 2b: Determine detection prompt
        if request.apiKey:
            _log.debug(f"[{analysis_id}] VLM detection with apiKey=****")
            try:
                detected_classes, detected_scene = await vlm_detect(image, request.apiKey)
                effective_prompt = ".".join(detected_classes)
                timings["4a_vlm"] = _t() - t_last; t_last = _t()
                _log.info(f"[{analysis_id}] 4a_vlm: {timings['4a_vlm']*1000:.0f}ms  scene='{detected_scene}' classes={detected_classes}")
            except Exception as e:
                _log.warning(f"[{analysis_id}] VLM failed ({e}), falling back to auto-prompt")
                inferred_scene = infer_scene_from_image(image)
                effective_prompt = get_auto_prompt(inferred_scene)
                detected_scene = inferred_scene
                detected_classes = [c.strip() for c in effective_prompt.split(".") if c.strip()]
                timings["4a_vlm_fallback"] = _t() - t_last; t_last = _t()
                _log.info(f"[{analysis_id}] 4a_vlm_fallback: {timings['4a_vlm_fallback']*1000:.0f}ms  scene='{inferred_scene}'")
        else:
            inferred_scene = infer_scene_from_image(image)
            effective_prompt = get_auto_prompt(inferred_scene)
            detected_scene = inferred_scene
            detected_classes = [c.strip() for c in effective_prompt.split(".") if c.strip()]
            timings["4b_auto_prompt"] = _t() - t_last; t_last = _t()
            _log.info(f"[{analysis_id}] 4b_auto_prompt: {timings['4b_auto_prompt']*1000:.0f}ms  scene='{inferred_scene}'")

        # Step 3: Grounding DINO detection
        detections = model_manager.grounding_dino.detect(
            image, prompt=effective_prompt, threshold=0.3
        )
        timings["5_dino"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 5_dino: {timings['5_dino']*1000:.0f}ms  boxes={len(detections)}")

        if not detections:
            _log.info(f"[{analysis_id}] No DINO detections — falling back to SAM2 auto masks only")
            auto_masks = model_manager.sam2.predict_automatic_masks(image)
            timings["5b_auto_masks"] = _t() - t_last; t_last = _t()
            _log.info(f"[{analysis_id}] 5b_auto_masks: {timings['5b_auto_masks']*1000:.0f}ms  found={len(auto_masks)}")

            objects = _build_objects_from_auto_masks(
                auto_masks, depth_m, w, h, analysis_id,
                image_area=w * h,
            )
            layers = build_spatial_layers_from_objects(objects, depth_m, w, h)
            return {
                "analysisId": analysis_id,
                "depthMapUrl": depth_url,
                "objects": objects,
                "layers": layers,
                "sceneGraph": {"shotId": request.shotId, "nodes": []},
                "vlmDetectedClasses": detected_classes,
                "vlmDetectedScene": detected_scene,
            }

        # Get boxes and scores for SAM2
        boxes = np.array([d.box for d in detections])
        scores = np.array([d.score for d in detections])

        # SAM2 segmentation from detection boxes
        image_np = np.array(image)
        masks_and_scores = model_manager.sam2.predict_masks_from_boxes(
            image_np, boxes, scores
        )
        timings["6_sam2_from_boxes"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 6_sam2_from_boxes: {timings['6_sam2_from_boxes']*1000:.0f}ms  masks={len(masks_and_scores)}")

        # Edge refinement: snap mask contours to Canny edges
        masks_and_scores = refine_mask_edges(masks_and_scores, image_np, snap_distance=8)
        timings["7_edge_refine"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 7_edge_refine: {timings['7_edge_refine']*1000:.0f}ms")

        # Filter out tiny masks
        masks_and_scores = filter_small_masks(masks_and_scores, min_area=500)

        # Step 3b: SAM2 automatic masks for coverage gap filling
        auto_masks = model_manager.sam2.predict_automatic_masks(image)
        timings["8_sam2_auto"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 8_sam2_auto: {timings['8_sam2_auto']*1000:.0f}ms  found={len(auto_masks)}")

        # Build SpatialObject list from DINO+SAM2 detections
        dino_objects = _build_objects_from_dino_detections(
            masks_and_scores, detections, depth_m, w, h, analysis_id,
        )
        timings["9_build_dino_objects"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 9_build_dino_objects: {timings['9_build_dino_objects']*1000:.0f}ms  count={len(dino_objects)}")

        # Build SpatialObject list from SAM2 auto masks (pre-filtered + area-limited)
        auto_objects = _build_objects_from_auto_masks(
            auto_masks, depth_m, w, h, analysis_id,
            image_area=w * h,
        )
        timings["10_build_auto_objects"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 10_build_auto_objects: {timings['10_build_auto_objects']*1000:.0f}ms  count={len(auto_objects)}")

        # Merge: prefer DINO detections (they have semantic labels).
        merged_objects = _merge_dino_and_auto_objects(
            dino_objects, auto_objects, iou_threshold=AUTO_IOU_THRESHOLD,
        )
        timings["11_merge"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 11_merge: {timings['11_merge']*1000:.0f}ms  final={len(merged_objects)} (DINO={len(dino_objects)}, auto={len(auto_objects)})")

        # Step 4: Build spatial layers
        layers = build_spatial_layers_from_objects(merged_objects, depth_m, w, h)
        timings["12_layers"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 12_layers: {timings['12_layers']*1000:.0f}ms")

        # Step 5: Build scene graph
        scene_graph = build_scene_graph_from_objects(request.shotId, merged_objects)
        timings["13_scene_graph"] = _t() - t_last; t_last = _t()
        _log.info(f"[{analysis_id}] 13_scene_graph: {timings['13_scene_graph']*1000:.0f}ms  nodes={len(scene_graph.get('nodes', []))}")

        # Meter-based layer thresholds (foreground/midground/background/sky in meters)
        depth_buckets_response = [
            {"name": name, "zMin": float(z_min), "zMax": float(z_max) if z_max != float("inf") else 9999.0}
            for z_min, z_max, name in settings.depth_buckets
        ]

        total_ms = sum(timings.values()) * 1000
        _log.info(f"[{analysis_id}] === Pipeline done: {total_ms:.0f}ms total ===")
        for name, sec in timings.items():
            _log.info(f"[{analysis_id}]   {name}: {sec*1000:.0f}ms ({sec/total_ms*100:.0f}%)")

        response = {
            "analysisId": analysis_id,
            "depthMapUrl": depth_url,
            "objects": merged_objects,
            "layers": layers,
            "sceneGraph": scene_graph,
            "vlmDetectedClasses": detected_classes,
            "vlmDetectedScene": detected_scene,
            "depthBuckets": depth_buckets_response,
        }
        return response

    except Exception as e:
        _log.error(f"[{analysis_id}] Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _build_objects_from_dino_detections(
    masks_and_scores: list[tuple[np.ndarray, float]],
    detections,
    depth_m: np.ndarray,
    w: int, h: int,
    analysis_id: str,
) -> list[dict]:
    """Build a list of SpatialObject dicts from DINO+SAM2 results."""
    objects = []
    for i, (mask, score) in enumerate(masks_and_scores):
        det = detections[i]
        masked_depth = np.where(mask, depth_m, np.nan)
        raw_median = float(np.nanmedian(masked_depth))
        obj_depth = raw_median if not np.isnan(raw_median) else (float(np.nanmean(masked_depth)) if not np.isnan(float(np.nanmean(masked_depth))) else 0.0)
        layer_name, _, _ = assign_to_depth_layer(obj_depth)

        mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
        obj_id = det.object_id
        _store_mask(obj_id, pil_to_base64(mask_img))
        norm_bbox = bbox_to_xywh(det.box, w, h)
        polygon = extract_polygon_from_mask(mask)

        objects.append({
            "id": obj_id,
            "classLabel": det.label,
            "depth": round(obj_depth, 2),
            "boundingBox": norm_bbox,
            "maskDataUrl": "",
            "polygon": polygon,
            "layer": layer_name,
        })
    return objects


def _build_objects_from_auto_masks(
    auto_masks: list[dict],
    depth_m: np.ndarray,
    w: int, h: int,
    analysis_id: str,
    image_area: int,
) -> list[dict]:
    """
    Build SpatialObject dicts from SAM2 automatic masks.

    Filters:
    - MIN_AREA_RATIO: mask must cover at least 0.2% of image area
    - MAX_AUTOMASKS: keep only top-100 by area (largest first)
    - Small mask fallback (< 500 px) always discarded
    """
    # 1. Area + ratio filter
    min_area = max(500, int(image_area * MIN_AREA_RATIO))

    filtered = []
    for m in auto_masks:
        mask = m["segmentation"]
        area = int(mask.sum())
        if area < min_area:
            continue
        filtered.append((area, m))

    # 2. Keep only top-N by area
    filtered.sort(key=lambda x: x[0], reverse=True)
    filtered = filtered[:MAX_AUTOMASKS]

    objects = []
    counter = 1
    for area, m in filtered:
        mask = m["segmentation"]
        bbox = m.get("bbox", [0, 0, 0, 0])
        masked_depth = np.where(mask, depth_m, np.nan)
        raw_median = float(np.nanmedian(masked_depth))
        obj_depth = raw_median if not np.isnan(raw_median) else (float(np.nanmean(masked_depth)) if not np.isnan(float(np.nanmean(masked_depth))) else 0.0)
        layer_name, _, _ = assign_to_depth_layer(obj_depth)

        mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
        obj_id = f"auto_{analysis_id}_{counter}"
        _store_mask(obj_id, pil_to_base64(mask_img))

        norm_bbox = {
            "x": float(bbox[0] / w),
            "y": float(bbox[1] / h),
            "w": float((bbox[2] - bbox[0]) / w),
            "h": float((bbox[3] - bbox[1]) / h),
        }
        polygon = extract_polygon_from_mask(mask)

        objects.append({
            "id": obj_id,
            "classLabel": f"object_{counter}",
            "depth": round(obj_depth, 2),
            "boundingBox": norm_bbox,
            "maskDataUrl": "",
            "polygon": polygon,
            "layer": layer_name,
        })
        counter += 1

    return objects


def _merge_dino_and_auto_objects(
    dino_objects: list[dict],
    auto_objects: list[dict],
    iou_threshold: float = 0.6,
) -> list[dict]:
    """
    Merge DINO detections with SAM2 auto masks.

    Two-phase approach:
    1. All DINO results are kept (they have semantic class labels).
    2. Auto masks that overlap (IoU > threshold) with any DINO box are discarded
       — they are already covered by labeled detections.
    3. Remaining auto masks (no DINO overlap) are appended as unlabeled objects.

    Returns the merged list (DINO first, then unique auto masks).
    """
    if not dino_objects:
        return auto_objects
    if not auto_objects:
        return dino_objects

    # Build a quick lookup of DINO boxes for IoU checking
    auto_kept = []
    for auto_obj in auto_objects:
        auto_bbox = auto_obj["boundingBox"]
        overlap = False
        for dino_obj in dino_objects:
            dino_bbox = dino_obj["boundingBox"]
            iou = _bbox_iou(auto_bbox, dino_bbox)
            if iou > iou_threshold:
                overlap = True
                break
        if not overlap:
            auto_kept.append(auto_obj)

    return dino_objects + auto_kept


def _bbox_iou(a: dict, b: dict) -> float:
    """Compute IoU between two normalized {x, y, w, h} bounding boxes."""
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter = inter_w * inter_h
    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/depth — Depth map only
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/depth")
async def generate_depth(request: DepthRequest):
    """
    Generate a depth map + depth-based segmentation from an image.

    Pipeline (no DINO, no VLM):
      1. DepthAnything V2 → depth map
      2. SAM2 automatic masks (full coverage, no detection prompt)
      3. Per-mask median depth → assign to depth layer
      4. Return depth map + objects + percentile depth bounds for client-side
         K-layer slicing

    Response:
      - depthMapUrl: base64 PNG (full-resolution, 0-1 normalized → gray)
      - objects: same shape as analyze() objects[], with classLabel = depth_obj_N
      - depthBounds: 11 quantiles (q0..q100) in meters — for client-side
        K-layer slicing
    """
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size
        analysis_id = f"depth_{uuid.uuid4().hex[:8]}"

        # 1. DepthAnything V2
        depth_norm = model_manager.depth_model.predict(image)
        depth_m = depth_to_meters(depth_norm, scale=50.0)

        # 2. Depth map PNG (served as static file, not base64)
        depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
        depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)
        depth_url = pil_to_file(depth_pil_resized, f"depth_{analysis_id}.png")

        # 3. SAM2 automatic masks
        auto_masks = model_manager.sam2.predict_automatic_masks(image)
        image_area = w * h

        # 4. Build objects (same shape as analyze(), no DINO/VLM)
        objects = _build_depth_objects_from_auto_masks(
            auto_masks, depth_m, w, h, analysis_id, image_area,
        )

        # 5. Depth percentile bounds (q0, q10, q20, ..., q100) — 11 values
        depth_values = depth_m.flatten()
        depth_values = depth_values[~np.isnan(depth_values)]
        depth_bounds = [
            {"q": q, "value": float(np.percentile(depth_values, q))}
            for q in range(0, 101, 10)
        ]

        depth_buckets_response = [
            {"name": name, "zMin": float(z_min), "zMax": float(z_max) if z_max != float("inf") else 9999.0}
            for z_min, z_max, name in settings.depth_buckets
        ]

        return {
            "depthMapUrl": depth_url,
            "objects": objects,
            "depthBounds": depth_bounds,
            "depthBuckets": depth_buckets_response,
        }
    except Exception as e:
        _log.error(f"[{analysis_id}] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _build_depth_objects_from_auto_masks(
    auto_masks: list[dict],
    depth_m: np.ndarray,
    w: int, h: int,
    analysis_id: str,
    image_area: int,
) -> list[dict]:
    """
    Build SpatialObject dicts from SAM2 automatic masks for depth mode.
    Same as _build_objects_from_auto_masks but uses depth-layer naming
    (no DINO class labels) and assigns layer purely by depth.
    """
    min_area = max(500, int(image_area * MIN_AREA_RATIO))

    filtered = []
    for m in auto_masks:
        mask = m["segmentation"]
        area = int(mask.sum())
        if area < min_area:
            continue
        filtered.append((area, m))

    filtered.sort(key=lambda x: x[0], reverse=True)
    filtered = filtered[:MAX_AUTOMASKS]

    objects = []
    counter = 1
    for area, m in filtered:
        mask = m["segmentation"]
        bbox = m.get("bbox", [0, 0, 0, 0])
        masked_depth = np.where(mask, depth_m, np.nan)
        raw_median = float(np.nanmedian(masked_depth))
        obj_depth = raw_median if not np.isnan(raw_median) else (
            float(np.nanmean(masked_depth)) if not np.isnan(float(np.nanmean(masked_depth))) else 0.0
        )
        layer_name, _, _ = assign_to_depth_layer(obj_depth)

        mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
        obj_id = f"depth_obj_{analysis_id}_{counter}"
        _store_mask(obj_id, pil_to_base64(mask_img))

        norm_bbox = {
            "x": float(bbox[0] / w),
            "y": float(bbox[1] / h),
            "w": float((bbox[2] - bbox[0]) / w),
            "h": float((bbox[3] - bbox[1]) / h),
        }
        polygon = extract_polygon_from_mask(mask)

        objects.append({
            "id": obj_id,
            "classLabel": f"depth_obj_{counter}",
            "depth": round(obj_depth, 2),
            "boundingBox": norm_bbox,
            "maskDataUrl": "",
            "polygon": polygon,
            "layer": layer_name,
        })
        counter += 1

    return objects


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/segment — Object segmentation only
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/segment")
async def segment_objects(request: SegmentRequest):
    """Detect and segment objects using Grounding DINO + SAM2."""
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size
        image_np = np.array(image)

        # Get depth for depth estimation
        depth_norm = model_manager.depth_model.predict(image)
        depth_m = depth_to_meters(depth_norm, scale=50.0)

        # Determine prompt: VLM-enhanced or local auto-prompt
        if request.apiKey:
            _log.debug(f"[segment] VLM detection with apiKey=****")
            try:
                detected_classes, detected_scene = await vlm_detect(image, request.apiKey)
                prompt = ".".join(detected_classes)
                print(f"[segment] VLM scene='{detected_scene}' classes={detected_classes}")
            except Exception as e:
                _log.warning(f"[segment] VLM failed ({e}), falling back to auto-prompt")
                inferred_scene = infer_scene_from_image(image)
                prompt = get_auto_prompt(inferred_scene)
                detected_classes = [c.strip() for c in prompt.split(".") if c.strip()]
                detected_scene = inferred_scene
        else:
            inferred_scene = infer_scene_from_image(image)
            prompt = get_auto_prompt(inferred_scene)
            detected_classes = [c.strip() for c in prompt.split(".") if c.strip()]
            detected_scene = inferred_scene
            print(f"[segment] Auto prompt scene='{inferred_scene}'")

        detections = model_manager.grounding_dino.detect(image, prompt=prompt, threshold=0.3)

        if not detections:
            return {"objects": []}

        boxes = np.array([d.box for d in detections])
        scores = np.array([d.score for d in detections])

        masks_and_scores = model_manager.sam2.predict_masks_from_boxes(image_np, boxes, scores)
        masks_and_scores = refine_mask_edges(masks_and_scores, image_np, snap_distance=8)

        objects = []
        for i, (mask, _) in enumerate(masks_and_scores):
            det = detections[i]
            masked_depth = np.where(mask, depth_m, np.nan)
            raw_median = float(np.nanmedian(masked_depth))
            obj_depth = raw_median if not np.isnan(raw_median) else (float(np.nanmean(masked_depth)) if not np.isnan(float(np.nanmean(masked_depth))) else 0.0)
            layer_name, _, _ = assign_to_depth_layer(obj_depth)

            mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
            obj_id = det.object_id
            _store_mask(obj_id, pil_to_base64(mask_img))
            norm_bbox = bbox_to_xywh(det.box, w, h)

            polygon = extract_polygon_from_mask(mask)

            objects.append({
                "id": obj_id,
                "classLabel": det.label,
                "depth": round(obj_depth, 2),
                "boundingBox": norm_bbox,
                "maskDataUrl": "",
                "polygon": polygon,
                "layer": layer_name,
            })

        return {"objects": objects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/layers — Build spatial layers
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/layers")
async def build_layers(request: LayersRequest):
    """Build spatial layers from a depth map and object list."""
    try:
        depth_img = base64_to_pil(request.depthMap)
        depth_img = depth_img.convert("L").resize((request.imageWidth, request.imageHeight), Image.LANCZOS)
        depth_np = np.array(depth_img).astype(np.float32) / 255.0
        depth_m = depth_to_meters(depth_np, scale=50.0)

        # Update object depths using the depth map
        for obj in request.objects:
            obj_depth = estimate_depth_from_bbox(
                depth_m,
                obj.get("boundingBox", {}),
                request.imageWidth,
                request.imageHeight,
            )
            obj["depth"] = round(obj_depth, 2)
            layer_name, _, _ = assign_to_depth_layer(obj_depth)
            obj["layer"] = layer_name

        layers = build_spatial_layers_from_objects(request.objects, depth_m, request.imageWidth, request.imageHeight)
        return {"layers": layers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/scene-graph — Build scene graph
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/scene-graph")
async def build_graph(request: SceneGraphRequest):
    """Build spatial relationship graph from objects."""
    try:
        graph = build_scene_graph_from_objects(request.shotId, request.objects)
        return {"sceneGraph": graph}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/billboard — Generate RGBA billboard
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/billboard")
async def generate_billboard(request: BillboardRequest):
    """
    Generate an RGBA billboard texture for a cropped object.
    Uses the mask to cut out the subject and apply transparency.
    """
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size

        # Build polygon mask if polygon points provided, else fall back to bbox
        raw_polygon = getattr(request, 'polygon', None)
        polygon = raw_polygon if (raw_polygon is not None and len(raw_polygon) > 0) else []
        _log.info(f"[billboard] objectId=%s polygon_points=%s bbox=%s", request.objectId, len(polygon), request.boundingBox)

        if polygon and len(polygon) >= 3:
            # Full-image polygon mask
            mask_np = np.zeros((h, w), dtype=np.uint8)
            pts = np.array([[int(px * w), int(py * h)] for [px, py] in polygon], dtype=np.int32)
            if pts.shape[0] < 3:
                raise ValueError(f"Polygon has fewer than 3 points: {pts.shape}")
            cv2.fillPoly(mask_np, [pts], 255)
            # Crop to tight bbox of polygon
            xs, ys = pts[:, 0], pts[:, 1]
            px1, px2 = int(xs.min()), int(xs.max())
            py1, py2 = int(ys.min()), int(ys.max())
            px1, py1 = max(0, px1), max(0, py1)
            px2, py2 = min(w, px2), min(h, py2)
            if px2 <= px1 or py2 <= py1:
                raise ValueError(f"Invalid polygon crop region: ({px1},{py1})-({px2},{py2})")
            cropped = image.crop((px1, py1, px2, py2))
            mask_cropped = mask_np[py1:py2, px1:px2]
        else:
            # Rectangle fallback
            bbox = request.boundingBox
            x1 = int(bbox["x"] * w)
            y1 = int(bbox["y"] * h)
            bw = int(bbox["w"] * w)
            bh = int(bbox["h"] * h)
            x2, y2 = x1 + bw, y1 + bh
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            cropped = image.crop((x1, y1, x2, y2))
            mask_np = np.zeros((h, w), dtype=np.uint8)
            mask_np[y1:y2, x1:x2] = 255
            mask_cropped = mask_np[y1:y2, x1:x2]

        rgba = create_rgba_from_masked_image(cropped, mask_cropped)
        return {"billboardUrl": pil_to_base64(rgba, fmt="PNG")}
    except Exception as e:
        _log.exception(f"[billboard] ERROR objectId=%s: %s", request.objectId, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/multiface — Generate 6-face textures
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/multiface")
async def generate_multiface(request: MultifaceRequest):
    """
    Generate 6-face pseudo-3D textures for an object.
    - front: original image (cropped)
    - back: horizontal flip
    - left: -90 deg rotation
    - right: +90 deg rotation
    - top: small crop from top edge
    - bottom: small crop from bottom edge
    """
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size

        raw_polygon = getattr(request, 'polygon', None)
        polygon = raw_polygon if (raw_polygon is not None and len(raw_polygon) > 0) else []

        if polygon and len(polygon) >= 3:
            mask_np = np.zeros((h, w), dtype=np.uint8)
            pts = np.array([[int(px * w), int(py * h)] for [px, py] in polygon], dtype=np.int32)
            cv2.fillPoly(mask_np, [pts], 255)
            xs, ys = pts[:, 0], pts[:, 1]
            px1, px2 = int(xs.min()), int(xs.max())
            py1, py2 = int(ys.min()), int(ys.max())
            px1, py1 = max(0, px1), max(0, py1)
            px2, py2 = min(w, px2), min(h, py2)
            cropped = image.crop((px1, py1, px2, py2))
        else:
            bbox = request.boundingBox
            x1 = int(bbox["x"] * w)
            y1 = int(bbox["y"] * h)
            bw = int(bbox["w"] * w)
            bh = int(bbox["h"] * h)
            x2, y2 = x1 + bw, y1 + bh
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            cropped = image.crop((x1, y1, x2, y2))

        faces = {
            "front": pil_to_base64(cropped),
            "back": pil_to_base64(flip_image(cropped, "horizontal")),
            "left": pil_to_base64(rotate_image_90(cropped, -1)),   # CCW 90
            "right": pil_to_base64(rotate_image_90(cropped, 1)),    # CW 90
            "top": pil_to_base64(cropped.crop((0, 0, cropped.width, max(1, cropped.height // 4)))),
            "bottom": pil_to_base64(cropped.crop((0, max(0, cropped.height - cropped.height // 4), cropped.width, cropped.height))),
        }

        return {"faces": faces}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/inpaint — Inpaint with wanx2.1-imageedit
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/inpaint")
async def inpaint_image(request: InpaintRequest):
    """
    Inpaint the non-selected areas using DashScope wanx2.1-imageedit model.

    maskDataUrl should be an RGBA PNG where:
      - White (alpha=255): background — will be edited and inpainted
      - Black (alpha=0):   selected objects — will be retained
    prompt: describes what to fill in the white (edited) regions
    """
    effective_key = request.apiKey or settings.dashscope_api_key
    if not effective_key:
        raise HTTPException(
            status_code=503,
            detail="DashScope API key not configured. Pass apiKey in request body or set AICSS_DASHSCOPE_API_KEY env var.",
        )

    try:
        base_image = load_image_from_url_or_base64(request.imageUrl)
        mask_image = load_image_from_url_or_base64(request.maskDataUrl, keep_alpha=True)

        if base_image.size != mask_image.size:
            raise HTTPException(
                status_code=400,
                detail=f"Size mismatch: base_image={base_image.size}, mask={mask_image.size}. "
                       "Mask must have the same dimensions as the base image.",
            )

        result_img = generate_inpaint(
            base_image=base_image,
            mask_image=mask_image,
            prompt=request.prompt,
            api_key=effective_key,
        )

        result_url = pil_to_base64(result_img)
        return {"inpaintResultUrl": result_url}

    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"[inpaint] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/aicss/mask/{object_id} — Serve a single mask PNG on-demand
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/mask/{object_id}")
async def get_object_mask(object_id: str):
    """
    Return a single object mask as a PNG image.

    Masks are stored in-memory when /analyze or /segment builds objects.
    If not found, returns 404.
    """
    if object_id not in _MASK_STORE:
        raise HTTPException(status_code=404, detail=f"Mask not found for '{object_id}'")
    raw = base64.b64decode(_MASK_STORE[object_id])
    return Response(content=raw, media_type="image/png")
