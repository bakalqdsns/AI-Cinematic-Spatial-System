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


# ─── Paper Diorama 2.0 request models ─────────────────────────────────────────

class PaperStyleRequest(BaseModel):
    imageUrl: str = Field(..., description="Image URL or base64 data URL")
    colorLevels: int = Field(12, ge=3, le=30, description="Colour quantisation levels (lower = flatter)")
    styleStrength: float = Field(0.7, ge=0.0, le=1.0, description="Bilateral filter strength")
    edgeLow: int = Field(50, ge=0, le=255, description="Canny edge low threshold")
    edgeHigh: int = Field(150, ge=0, le=255, description="Canny edge high threshold")


class PaperDioramaRequest(BaseModel):
    imageUrl: str = Field(..., description="Full image URL or base64 data URL")
    maskDataUrl: str = Field(..., description="Object mask base64 PNG, 255=object, 0=background")
    thicknessMin: float = Field(1.0, ge=0.1, le=20.0, description="Min paper thickness in mm")
    thicknessMax: float = Field(5.0, ge=0.1, le=20.0, description="Max paper thickness in mm")
    outlineWidth: int = Field(3, ge=0, le=20, description="Paper-cut outline width in pixels")
    colorLevels: int = Field(12, ge=3, le=30, description="Colour quantisation levels")
    styleStrength: float = Field(0.7, ge=0.0, le=1.0, description="Style smoothing strength")


class PaperLayerRequest(BaseModel):
    """
    Generate paper-diorama texture for a full depth layer (not just one object).

    与 PaperDioramaRequest 的区别：
      - PaperDiorama：切割单个物体的 mask，将物体转为纸模纹理（逐 object）
      - PaperLayer  ：对整层图像应用纸模效果，可选叠加 layerMask（逐 depth layer）
    """
    layerImageUrl: str = Field(..., description="Layer image URL or base64 data URL (RGBA PNG)")
    layerMaskUrl: Optional[str] = Field(None, description="Optional layer mask base64 PNG")
    thicknessMin: float = Field(1.0, ge=0.1, le=20.0)
    thicknessMax: float = Field(5.0, ge=0.1, le=20.0)
    outlineWidth: int = Field(3, ge=0, le=20)
    colorLevels: int = Field(12, ge=3, le=30)
    styleStrength: float = Field(0.7, ge=0.0, le=1.0)


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
        # scale=50.0 将深度图像素值线性映射到米：pixel_value (0-255) → depth_m = pixel * 50.0 / 255.0
        # 即最远可表示 ~50m，与室内场景和大多数电影镜头场景吻合
        depth_m = depth_to_meters(depth_norm, scale=50.0)

        # Convert depth to base64 PNG
        depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
        depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)
        depth_url = pil_to_base64(depth_pil_resized)

        # Step 2b: VLM 检测 — 始终运行，需要 API Key。
        # 与深度估计并行启动（asyncio.create_task），避免串行执行带来的额外延迟。
        # VLM 返回的类别列表直接拼成 "." 分隔字符串，作为 Grounding DINO 的检测提示词。
        print(f"[{analysis_id}] Running VLM detection with apiKey={request.apiKey[:12]}...")
        import asyncio
        vlm_task = asyncio.create_task(vlm_detect(image, request.apiKey))
        # 将控制权交还给事件循环，使深度估计能够同时执行
        detected_classes, detected_scene = await vlm_task
        # Grounding DINO 使用 "." 作为类别之间的分隔符，因此用 "." 拼接
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

        # SAM2 分割完成后，对每个预测 mask 进行边缘细化：
        # 用 Canny 边缘检测原图，将 mask 轮廓上的像素吸附到距离最近的 Canny 边缘。
        # 这样可以消除 SAM2 软边界导致的锯齿和毛边，使 paper-cut 纹理效果更干净锐利。
        print(f"[{analysis_id}] Refining mask edges...")
        image_np = np.array(image)
        masks_and_scores = refine_mask_edges(masks_and_scores, image_np, snap_distance=8)

        # Build SpatialObject list
        objects = []
        for i, (mask, score) in enumerate(masks_and_scores):
            det = detections[i]
            # 从 mask 覆盖区域内取深度值的中位数（忽略 NaN）：
            # nanmedian 比普通 median 更鲁棒，因为 mask 边缘像素可能位于深度图的有效区域之外，
            # 直接求 median 会受到边缘无效值干扰；nanmedian 自动跳过这些无效像素。
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

        # depth_model 用于估计每个检测到的物体实例的深度值（用于分配到深度层）。
        # 虽然标注为"segment only"，但深度是 assign_to_depth_layer 的必要输入，无法省略。
        # 如果不需要深度信息，请直接使用 segment endpoint 而不传 apiKey。
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
            # 多边形裁剪流程：
            #   1. 用 cv2.fillPoly 在全图尺寸上绘制多边形蒙版（255=保留区域）
            #   2. 计算多边形边界框，裁剪出最小矩形区域
            #   3. 从全图蒙版中同步裁剪对应区域，与图像保持尺寸一致
            # polygon 优先于 boundingBox：多边形能精确跟随物体轮廓，矩形会包含多余背景
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
            # 矩形兜底裁剪：用 boundingBox 坐标在原图上切出物体区域
            # mask_np 同样在全图尺寸上创建（而非直接创建 crop 尺寸），
            # 以便与 polygon 分支共用同一套 mask 处理逻辑（create_rgba_from_masked_image）
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
    # 优先级：请求体 apiKey > 环境变量 AICSS_DASHSCOPE_API_KEY
    # 若两者均未提供，返回 503 而非 500，方便前端区分"未配置"与"服务器错误"
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


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/paper-style — Paper illustration style transfer
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/paper-style")
async def paper_style_transfer(request: PaperStyleRequest):
    """
    Convert a photograph to paper-cut / illustration style.
    Applies bilateral filtering + colour quantisation + edge detection.
    """
    try:
        image = await _load_image(request.imageUrl)
        from app.utils.paper_diorama import cartoonize_image
        styled = cartoonize_image(
            image,
            color_quantization_levels=request.colorLevels,
            bilateral_filter_sigma_color=request.styleStrength * 10,
            bilateral_filter_sigma_space=request.styleStrength * 10,
            edge_canny_low=request.edgeLow,
            edge_canny_high=request.edgeHigh,
        )
        return {"styledImageUrl": pil_to_base64(styled, fmt="PNG")}
    except Exception as e:
        _log.exception("[paper-style] Error")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/paper-diorama — Full diorama texture set for one object
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/paper-diorama")
async def paper_diorama_generate(request: PaperDioramaRequest):
    """
    Generate a complete paper-diorama texture set for a single object:
      - paper_style_url    : illustrated paper style image
      - thickness_url      : thickness/height field (false-colour PNG)
      - normal_map_url     : surface normal map
      - outlined_url       : paper-style image with cut edges + shadow
      - thickness_gray_url : thickness as grayscale PNG
    """
    try:
        image = await _load_image(request.imageUrl)

        if request.maskDataUrl.startswith("data:"):
            import base64
            from io import BytesIO
            raw = request.maskDataUrl.split(",", 1)[1]
            data = base64.b64decode(raw)
            mask_pil = Image.open(BytesIO(data)).convert("L")
        else:
            import requests as _requests
            resp = _requests.get(request.maskDataUrl, timeout=30)
            resp.raise_for_status()
            from io import BytesIO as _BytesIO
            mask_pil = Image.open(_BytesIO(resp.content)).convert("L")

        if mask_pil.size != image.size:
            mask_pil = mask_pil.resize(image.size, Image.LANCZOS)

        mask = np.array(mask_pil)
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        from app.utils.paper_diorama import generate_paper_diorama_textures
        textures = generate_paper_diorama_textures(
            image=image,
            mask=mask,
            thickness_range_mm=(request.thicknessMin, request.thicknessMax),
            outline_width=request.outlineWidth,
            color_levels=request.colorLevels,
            style_strength=request.styleStrength,
        )
        return textures
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("[paper-diorama] Error")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/paper-layer — Paper diorama texture for a depth layer
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/paper-layer")
async def paper_layer_generate(request: PaperLayerRequest):
    """
    Generate paper-diorama texture for a full depth layer image.
    Returns the same texture fields as /paper-diorama.
    """
    try:
        image = await _load_image(request.layerImageUrl)

        if request.layerMaskUrl:
            mask_pil = base64_to_pil(request.layerMaskUrl).convert("L")
        else:
            mask_pil = Image.new("L", image.size, 255)

        if mask_pil.size != image.size:
            mask_pil = mask_pil.resize(image.size, Image.LANCZOS)

        mask = np.array(mask_pil)
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        from app.utils.paper_diorama import generate_paper_diorama_textures
        textures = generate_paper_diorama_textures(
            image=image,
            mask=mask,
            thickness_range_mm=(request.thicknessMin, request.thicknessMax),
            outline_width=request.outlineWidth,
            color_levels=request.colorLevels,
            style_strength=request.styleStrength,
        )
        return textures
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[paper-layer] Error: {e}\n{tb}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
