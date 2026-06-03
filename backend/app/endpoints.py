"""
AICSS API Endpoints.

All endpoints for the AICSS inference pipeline:
  POST /api/aicss/analyze       — Full pipeline (depth + segment + layers + graph)
  POST /api/aicss/depth         — Depth map only
  POST /api/aicss/segment       — Object segmentation only
  POST /api/aicss/layers        — Build spatial layers
  POST /api/aicss/scene-graph   — Build scene graph
  POST /api/aicss/billboard     — Generate RGBA billboard texture
  POST /api/aicss/multiface     — Generate 6-face pseudo-3D textures
"""
import io
import base64
import uuid
import time
import logging
from typing import Optional

import httpx
import torch
import numpy as np
import cv2

_log = logging.getLogger("aicss")
from PIL import Image
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings, DEVICE
from app.models.model_manager import model_manager
from app.utils.image_utils import (
    load_image_from_url_or_base64,
    pil_to_base64,
    base64_to_pil,
    numpy_to_pil_depth,
    depth_to_meters,
    create_layer_mask,
    apply_mask_to_image,
    create_rgba_from_masked_image,
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


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class ImageUrlRequest(BaseModel):
    imageUrl: str = Field(..., description="Image URL or base64 data URL")
    shotId: Optional[str] = Field(None, description="Optional shot ID for tracking")


class AnalyzeRequest(BaseModel):
    imageUrl: str
    shotId: str
    apiKey: str = Field(..., description="DashScope API key — required for VLM detection")


class DepthRequest(BaseModel):
    imageUrl: str


class SegmentRequest(BaseModel):
    imageUrl: str
    apiKey: str = Field(..., description="DashScope API key — required for VLM detection")


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
    """Load image from URL or base64."""
    return load_image_from_url_or_base64(url)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/analyze — Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """
    Full AICSS analysis pipeline.

    1. Load image
    2. Run DepthAnything V2 → depth map
    3. Run Grounding DINO + SAM2 → object masks
    4. Assign objects to spatial layers
    5. Build scene graph
    6. Return all results
    """
    analysis_id = f"aicss_{uuid.uuid4().hex[:8]}"

    try:
        # Step 1: Load image
        print(f"[{analysis_id}] Loading image from {request.imageUrl[:50]}...")
        image = await _load_image(request.imageUrl)
        w, h = image.size

        # Step 2: Depth estimation (start immediately)
        print(f"[{analysis_id}] Running depth estimation...")
        depth_norm = model_manager.depth_model.predict(image)
        depth_m = depth_to_meters(depth_norm, scale=50.0)

        # Convert depth to base64 PNG
        depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
        depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)
        depth_url = pil_to_base64(depth_pil_resized)

        # Step 2b: VLM detection — always runs. Key is required.
        # Runs concurrently with depth estimation to avoid adding latency.
        print(f"[{analysis_id}] Running VLM detection with apiKey={request.apiKey[:12]}...")
        import asyncio
        vlm_task = asyncio.create_task(vlm_detect(image, request.apiKey))
        # Yield to event loop so depth estimation can finish concurrently
        detected_classes, detected_scene = await vlm_task
        effective_prompt = ".".join(detected_classes)
        print(f"[{analysis_id}] VLM scene='{detected_scene}' classes={detected_classes}")

        # Step 3: Object detection + segmentation
        print(f"[{analysis_id}] Running Grounding DINO + SAM2 with prompt: {effective_prompt[:60]}...")
        detections = model_manager.grounding_dino.detect(image, prompt=effective_prompt, threshold=0.3)

        if not detections:
            print(f"[{analysis_id}] No objects detected.")
            return {
                "analysisId": analysis_id,
                "depthMapUrl": depth_url,
                "objects": [],
                "layers": [],
                "sceneGraph": {"shotId": request.shotId, "nodes": []},
                "vlmDetectedClasses": detected_classes,
                "vlmDetectedScene": detected_scene,
            }

        # Get boxes and scores for SAM2
        boxes = np.array([d.box for d in detections])
        scores = np.array([d.score for d in detections])
        labels = [d.label for d in detections]

        # SAM2 segmentation
        masks_and_scores = model_manager.sam2.predict_masks_from_boxes(
            np.array(image), boxes, scores
        )

        # Edge refinement: snap each mask contour to nearby Canny edges
        print(f"[{analysis_id}] Refining mask edges...")
        image_np = np.array(image)
        masks_and_scores = refine_mask_edges(masks_and_scores, image_np, snap_distance=8)

        # Build SpatialObject list
        objects = []
        for i, (mask, score) in enumerate(masks_and_scores):
            det = detections[i]
            # Estimate depth from median in masked region
            masked_depth = np.where(mask, depth_m, np.nan)
            obj_depth = float(np.nanmedian(masked_depth))
            layer_name, _, _ = assign_to_depth_layer(obj_depth)

            # Encode mask as base64 PNG
            mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
            mask_url = pil_to_base64(mask_img)

            # Normalized bounding box
            norm_bbox = bbox_to_xywh(det.box, w, h)

            # Extract polygon contour
            polygon = extract_polygon_from_mask(mask)
            print(f"[{analysis_id}] {det.label}: mask sum={mask.sum()}, polygon points={len(polygon)}")

            objects.append({
                "id": det.object_id,
                "classLabel": det.label,
                "depth": round(obj_depth, 2),
                "boundingBox": norm_bbox,
                "maskDataUrl": mask_url,
                "polygon": polygon,
                "layer": layer_name,
            })

        # Step 4: Build spatial layers
        layers = build_spatial_layers_from_objects(objects, depth_m, w, h)

        # Step 5: Build scene graph
        scene_graph = build_scene_graph_from_objects(request.shotId, objects)

        return {
            "analysisId": analysis_id,
            "depthMapUrl": depth_url,
            "objects": objects,
            "layers": layers,
            "sceneGraph": scene_graph,
            "vlmDetectedClasses": detected_classes,
            "vlmDetectedScene": detected_scene,
        }

    except Exception as e:
        print(f"[{analysis_id}] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/depth — Depth map only
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/depth")
async def generate_depth(request: DepthRequest):
    """Generate a depth map from an image."""
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size
        depth_norm = model_manager.depth_model.predict(image)
        depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
        depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)
        return {"depthMapUrl": pil_to_base64(depth_pil_resized)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        # Always use VLM to detect classes
        print(f"[segment] Running VLM detection with apiKey={request.apiKey[:12]}...")
        import asyncio
        detected_classes, detected_scene = await asyncio.create_task(
            vlm_detect(image, request.apiKey)
        )
        prompt = ".".join(detected_classes)
        print(f"[segment] VLM scene='{detected_scene}' classes={detected_classes}")

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
            obj_depth = float(np.nanmedian(masked_depth))
            layer_name, _, _ = assign_to_depth_layer(obj_depth)

            mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
            mask_url = pil_to_base64(mask_img)
            norm_bbox = bbox_to_xywh(det.box, w, h)

            polygon = extract_polygon_from_mask(mask)

            objects.append({
                "id": det.object_id,
                "classLabel": det.label,
                "depth": round(obj_depth, 2),
                "boundingBox": norm_bbox,
                "maskDataUrl": mask_url,
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
        import traceback
        tb = traceback.format_exc()
        print(f"[inpaint] Error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
