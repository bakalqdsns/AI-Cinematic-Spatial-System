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
  POST /api/aicss/occlusion-holes — Auto occlusion hole masks for LaMa inpaint
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
from app.utils.inpaint_utils import (
    generate_inpaint,
    detect_weak_prompt,
    compute_mask_white_ratio,
)
from app.utils.vlm_utils import vlm_detect
from app.services.project_store import project_store


# ─────────────────────────────────────────────────────────────────────────────
# Project persistence helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _save_project_artifact(
    project_id: Optional[str],
    step: str,
    files: dict[str, bytes | dict],
) -> list[str] | None:
    """
    If project_id is set, save files to the project's <step>/ directory.
    Returns list of saved filenames, or None when project_id is not set.
    Failures are logged but never propagate — persistence is best-effort.
    """
    if not project_id:
        return None
    try:
        await project_store.save_step(project_id, step, files)
        return list(files.keys())
    except Exception as e:
        _log.warning(f"[project-store] save_step failed: {e}")
        return []


def _b64_png_to_pil(b64: str):
    """Decode base64 PNG (with or without data: prefix) to PIL Image."""
    import base64 as _b64
    from io import BytesIO as _BytesIO
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[1]
    return Image.open(_BytesIO(_b64.b64decode(b64)))


def _pil_to_png_bytes(pil_img) -> bytes:
    """Convert PIL Image to PNG bytes."""
    from io import BytesIO as _BytesIO
    buf = _BytesIO()
    if pil_img.mode not in ("RGB", "RGBA", "L"):
        pil_img = pil_img.convert("RGBA")
    pil_img.save(buf, format="PNG")
    return buf.getvalue()


def _sanitize_filename(name: str) -> str:
    """
    Sanitise an arbitrary string (objectId, layerKey, etc.) for use as a filename.
    Only keeps letters, digits, dot, dash, underscore. Other chars become '_'.
    Empty result is replaced by 'unnamed'.
    """
    import re as _re
    s = _re.sub(r"[^A-Za-z0-9_.\-]", "_", name or "")
    return s or "unnamed"


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class ImageUrlRequest(BaseModel):
    imageUrl: str = Field(..., description="Image URL or base64 data URL")
    shotId: Optional[str] = Field(None, description="Optional shot ID for tracking")


class AnalyzeRequest(BaseModel):
    imageUrl: str
    shotId: str
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, results are persisted to .workspace/projects/<id>/")


# ─────────────────────────────────────────────────────────────────────────────
# Response models (Phase 1.4.4 — v1 endpoint Pydantic responses)
#
# Previously every v1 endpoint returned ``-> dict``, which means OpenAPI
# couldn't expose the response schema and the frontend had to guess field
# names by reading the backend source. We now declare Pydantic models so
# the OpenAPI doc renders complete response shapes — and consumers can
# rely on field names documented here rather than chasing implementation
# details. Existing callers keep working because Pydantic models are
# JSON-serialisable.
# ─────────────────────────────────────────────────────────────────────────────


class DepthResponse(BaseModel):
    """`POST /api/aicss/depth` response."""
    depthMapUrl: str = Field(
        ..., description="Base64 data URI of the depth map PNG (grayscale)"
    )
    width: int = Field(..., description="Depth map width in pixels")
    height: int = Field(..., description="Depth map height in pixels")
    minDepth: float = Field(..., description="Minimum depth value (meters)")
    maxDepth: float = Field(..., description="Maximum depth value (meters)")
    savedFiles: Optional[list[str]] = Field(
        default=None,
        description="Filenames persisted under the project's `depth/` dir (when projectId was provided)",
    )


class SegmentResponse(BaseModel):
    """`POST /api/aicss/segment` response."""
    objects: list[dict] = Field(
        ...,
        description="Detected objects with `id`, `classLabel`, `boundingBox`, `mask`, etc.",
    )
    width: int
    height: int
    savedFiles: Optional[list[str]] = None


class LayersResponse(BaseModel):
    """`POST /api/aicss/layers` response."""
    layers: list[dict] = Field(
        ...,
        description="Per-layer entries with `name`, `zMin`, `zMax`, `objects`.",
    )
    width: int
    height: int
    savedFiles: Optional[list[str]] = None


class SceneGraphResponse(BaseModel):
    """`POST /api/aicss/scene-graph` response."""
    shotId: str
    nodes: list[dict] = Field(
        ...,
        description="Object nodes with relations (`leftOf`, `rightOf`, `inFrontOf`, `behind`, `above`, `below`).",
    )
    savedFiles: Optional[list[str]] = None


class AnalyzeResponse(BaseModel):
    """`POST /api/aicss/analyze` response — full pipeline output.

    The handler returns extra diagnostic fields (`analysisId`,
    `vlmDetectedClasses`, `vlmDetectedScene`) that aren't part of the
    core pipeline output but are useful for debugging and for the
    frontend to show the user which classes VLM detected. FastAPI's
    ``response_model_exclude_none=True`` would hide them on None; we
    instead expose them as Optional so the OpenAPI schema documents the
    real shape including diagnostic fields.
    """
    analysisId: Optional[str] = Field(
        default=None,
        description="Unique analysis run ID (for log correlation)",
    )
    shotId: Optional[str] = Field(
        default=None,
        description="Echoes the request's shotId so the frontend can correlate",
    )
    depthMapUrl: Optional[str] = None
    objects: list[dict] = Field(default_factory=list)
    layers: list[dict] = Field(default_factory=list)
    sceneGraph: Optional[dict] = None
    width: int = 0
    height: int = 0
    savedFiles: Optional[list[str]] = None
    vlmDetectedClasses: Optional[list[str]] = Field(
        default=None,
        description="Classes detected by the Qwen3-VL scene classifier (diagnostic)",
    )
    vlmDetectedScene: Optional[str] = Field(
        default=None,
        description="Scene type detected by VLM (outdoor/indoor/night/nature, diagnostic)",
    )


class InpaintResponse(BaseModel):
    """`POST /api/aicss/inpaint` response."""
    imageUrl: str = Field(..., description="Base64 data URI of the inpainted PNG")
    inpaintResultUrl: Optional[str] = Field(None, description="Alias of imageUrl, kept for backward compat")
    width: int
    height: int
    model: Optional[str] = Field(None, description="Model identifier used for inpainting")
    maskWhiteRatio: Optional[float] = Field(None, description="Ratio of white pixels in the mask")
    warnings: Optional[list[dict]] = None
    savedArtifacts: Optional[list[str]] = None
    usedFallback: bool = Field(
        default=False,
        description="True when the call fell back from cloud to local LaMa.",
    )
    savedFiles: Optional[list[str]] = None


class PaperDioramaResponse(BaseModel):
    """`POST /api/aicss/paper-diorama` response."""
    paperStyleUrl: Optional[str] = None
    normalMapUrl: Optional[str] = None
    thicknessGrayUrl: Optional[str] = None
    outlinedUrl: Optional[str] = None
    width: int = 0
    height: int = 0
    savedFiles: Optional[list[str]] = None


class PaperStyleResponse(BaseModel):
    """`POST /api/aicss/paper-style` response.

    Single-image cartoonisation — the input RGB image gets a flat paper-style
    texture applied. Distinct from `PaperDioramaResponse` which adds
    thickness/normal maps.
    """
    paperStyleUrl: Optional[str] = None
    width: int = 0
    height: int = 0
    savedFiles: Optional[list[str]] = None


class PaperLayerResponse(BaseModel):
    """`POST /api/aicss/paper-layer` response.

    Same texture set as `PaperDioramaResponse` but for an entire depth layer
    (e.g. the foreground layer of a scene). Adds a `layerKey` echo so the
    frontend can route the response back to the right layer.
    """
    paperStyleUrl: Optional[str] = None
    normalMapUrl: Optional[str] = None
    thicknessGrayUrl: Optional[str] = None
    outlinedUrl: Optional[str] = None
    width: int = 0
    height: int = 0
    savedFiles: Optional[list[str]] = None
    layerKey: Optional[str] = None


class BillboardResponse(BaseModel):
    """`POST /api/aicss/billboard` response."""
    rgbaUrl: Optional[str] = None
    billboardUrl: Optional[str] = None  # alias of rgbaUrl, kept for backward compat
    width: int = 0
    height: int = 0
    savedFiles: Optional[list[str]] = None


class MultifaceResponse(BaseModel):
    """`POST /api/aicss/multiface` response.

    Returns 6 RGBA PNGs — one per cube face. Useful for 3D viewers that
    need a quick pseudo-3D representation of a 2D object without
    running a full 3D reconstruction.
    """
    faces: dict[str, str] = Field(
        default_factory=dict,
        description="Map of face name (front/back/left/right/top/bottom) → "
                    "data:image/png;base64,... URI",
    )
    width: int = 0
    height: int = 0
    savedFiles: Optional[list[str]] = None


class DepthRequest(BaseModel):
    imageUrl: str
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, depth map is persisted")


class SegmentRequest(BaseModel):
    imageUrl: str
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, masks are persisted")


class LayersRequest(BaseModel):
    depthMap: str = Field(..., description="Base64-encoded depth PNG")
    objects: list[dict] = Field(..., description="List of SpatialObject dicts")
    imageWidth: int = Field(1024)
    imageHeight: int = Field(768)
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, layer images are persisted")


class SceneGraphRequest(BaseModel):
    shotId: str
    objects: list[dict]
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, scene graph is persisted")


class BillboardRequest(BaseModel):
    imageUrl: str
    objectId: str
    boundingBox: dict = Field(..., description="{x, y, w, h} normalized 0-1")
    polygon: list[list[float]] = Field(default_factory=list, description="[[x,y],...] normalized 0-1, overrides boundingBox for precise cropping")
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, billboard PNG is persisted")


class MultifaceRequest(BaseModel):
    imageUrl: str
    objectId: str
    boundingBox: dict = Field(..., description="{x, y, w, h} normalized 0-1")
    polygon: list[list[float]] = Field(default_factory=list, description="[[x,y],...] normalized 0-1, overrides boundingBox for precise cropping")
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, 6 face textures are persisted")


class InpaintRequest(BaseModel):
    imageUrl: str = Field(..., description="Image to inpaint, base64 or URL")
    maskDataUrl: str = Field(..., description="Mask (RGBA), white (alpha=255)=area to inpaint, black (alpha=0)=keep")
    prompt: str = Field(..., description="Inpainting prompt (for compatibility; LaMa performs blind inpainting)")
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, inpaint result is persisted")


class OcclusionHolesRequest(BaseModel):
    """从 Analyze 物体列表自动生成遮挡空洞 mask（不跑 LaMa）。"""
    objects: list[dict] = Field(..., description="DetectedObject[]（需含 id / maskDataUrl / depth / polygon）")
    imageWidth: int = Field(..., gt=0)
    imageHeight: int = Field(..., gt=0)
    targetObjectIds: Optional[list[str]] = Field(
        None, description="仅对这些 objectId 生成空洞；省略则全部"
    )
    mode: str = Field(
        "peel",
        description="peel=整物体 mask；occluded_interior=仅被更近物体遮挡的重叠区",
    )


class OcclusionHolesResponse(BaseModel):
    holes: list[dict]
    mergedMaskDataUrl: Optional[str] = None
    mode: str
    count: int


# ─── Paper Diorama 2.0 request models ─────────────────────────────────────────

class PaperStyleRequest(BaseModel):
    imageUrl: str = Field(..., description="Image URL or base64 data URL")
    colorLevels: int = Field(12, ge=3, le=30, description="Colour quantisation levels (lower = flatter)")
    styleStrength: float = Field(0.7, ge=0.0, le=1.0, description="Bilateral filter strength")
    edgeLow: int = Field(50, ge=0, le=255, description="Canny edge low threshold")
    edgeHigh: int = Field(150, ge=0, le=255, description="Canny edge high threshold")
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, styled image is persisted")


class PaperDioramaRequest(BaseModel):
    imageUrl: str = Field(..., description="Full image URL or base64 data URL")
    maskDataUrl: str = Field(..., description="Object mask base64 PNG, 255=object, 0=background")
    thicknessMin: float = Field(1.0, ge=0.1, le=20.0, description="Min paper thickness in mm")
    thicknessMax: float = Field(5.0, ge=0.1, le=20.0, description="Max paper thickness in mm")
    outlineWidth: int = Field(3, ge=0, le=20, description="Paper-cut outline width in pixels")
    colorLevels: int = Field(12, ge=3, le=30, description="Colour quantisation levels")
    styleStrength: float = Field(0.7, ge=0.0, le=1.0, description="Style smoothing strength")
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, 5 paper textures are persisted")


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
    projectId: Optional[str] = Field(None, description="Optional project ID — when set, 5 paper textures are persisted")
    layerKey: Optional[str] = Field(None, description="Optional depth layer key (foreground/midground/background/sky) — used for organising saved files")


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: load image
# ─────────────────────────────────────────────────────────────────────────────

async def _load_image(url: str) -> Image.Image:
    """Load image from URL or base64, preserving RGBA for mask extraction."""
    return load_image_from_url_or_base64(url, keep_alpha=True)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/analyze — Full pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
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

    # Pipeline-stage flags used by the final except block to return a meaningful
    # HTTP 503 (with the failing stage name) instead of a generic 500.
    _stage = "init"

    def _fail(stage: str, exc: Exception) -> None:
        """Record and raise a 503 with a per-stage diagnostic detail."""
        nonlocal _stage
        _stage = stage
        msg = f"[{stage}] {type(exc).__name__}: {exc}"
        # Truncate long exception messages (e.g., HF Hub errors can be huge)
        if len(msg) > 500:
            msg = msg[:500] + "...(truncated)"
        _log.error("[%s] %s", analysis_id, msg)
        _log.exception("[%s] Traceback", analysis_id)
        raise HTTPException(status_code=503, detail=msg)

    try:
        # ── Step 1: Load image ────────────────────────────────────────────────
        _stage = "image_load"
        _log.info("[%s] Loading image...", analysis_id)
        try:
            image = await _load_image(request.imageUrl)
            w, h = image.size
        except Exception as e:
            _fail("image_load", e)

        # ── Step 2: DepthAnything V2 ────────────────────────────────────────
        _stage = "depth"
        _log.info("[%s] Running depth estimation...", analysis_id)
        try:
            depth_norm = model_manager.depth_model.predict(image)
            # scale=50.0 将深度图像素值线性映射到米：pixel_value (0-255) → depth_m = pixel * 50.0 / 255.0
            # 即最远可表示 ~50m，与室内场景和大多数电影镜头场景吻合
            depth_m = depth_to_meters(depth_norm, scale=50.0)

            # Convert depth to base64 PNG
            depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
            depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)
            depth_url = pil_to_base64(depth_pil_resized)
        except Exception as e:
            _fail("depth", e)

        # Unload DepthAnything immediately — only depth_m numpy array needed from here on
        try:
            model_manager.unload_depth()
        except Exception as e:
            _log.warning("[%s] unload_depth failed (non-fatal): %s", analysis_id, e)

        # ── Step 2b: Qwen3-VL ───────────────────────────────────────────────
        _stage = "vlm"
        _log.info("[%s] Running VLM detection (local Qwen3-VL)...", analysis_id)
        import asyncio
        try:
            vlm_task = asyncio.create_task(vlm_detect(image))
            detected_classes, detected_scene = await vlm_task
        except Exception as e:
            _fail("vlm", e)
        effective_prompt = ".".join(detected_classes)
        _log.info("[%s] VLM scene='%s' classes=%s", analysis_id, detected_scene, detected_classes)

        # Unload Qwen3-VL immediately — only detected_classes list needed from here on
        try:
            model_manager.unload_qwen3vl()
        except Exception as e:
            _log.warning("[%s] unload_qwen3vl failed (non-fatal): %s", analysis_id, e)

        # ── Step 3: Grounding DINO ──────────────────────────────────────────
        _stage = "grounding_dino"
        _log.info("[%s] Running Grounding DINO...", analysis_id)
        try:
            detections = model_manager.grounding_dino.detect(image, prompt=effective_prompt, threshold=0.3)
        except Exception as e:
            _fail("grounding_dino", e)

        if not detections:
            _log.info("[%s] No objects detected.", analysis_id)
            return {
                "analysisId": analysis_id,
                "depthMapUrl": depth_url,
                "objects": [],
                "layers": [],
                "sceneGraph": {"shotId": request.shotId, "nodes": []},
                "vlmDetectedClasses": detected_classes,
                "vlmDetectedScene": detected_scene,
            }

        # Extract boxes/scores — numpy arrays, no model needed afterwards
        boxes = np.array([d.box for d in detections])
        scores = np.array([d.score for d in detections])
        labels = [d.label for d in detections]

        # Unload Grounding DINO immediately
        try:
            model_manager.unload_grounding_dino()
        except Exception as e:
            _log.warning("[%s] unload_grounding_dino failed (non-fatal): %s", analysis_id, e)

        # ── Step 4: SAM2 ────────────────────────────────────────────────────
        _stage = "sam2"
        _log.info("[%s] Running SAM2 segmentation...", analysis_id)
        try:
            masks_and_scores = model_manager.sam2.predict_masks_from_boxes(
                np.array(image), boxes, scores
            )
        except Exception as e:
            _fail("sam2", e)

        # Unload SAM2 immediately
        try:
            model_manager.unload_sam2()
        except Exception as e:
            _log.warning("[%s] unload_sam2 failed (non-fatal): %s", analysis_id, e)

        # ── Step 4b onwards: CPU post-processing (no model) ────────────────
        _stage = "post_process"
        _log.info("[%s] Refining mask edges...", analysis_id)
        try:
            image_np = np.array(image)
            masks_and_scores = refine_mask_edges(masks_and_scores, image_np, snap_distance=8)

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
                _log.debug("[%s] %s: mask sum=%s, polygon points=%d", analysis_id, det.label, mask.sum(), len(polygon))

                objects.append({
                    "id": det.object_id,
                    "classLabel": det.label,
                    "depth": round(obj_depth, 2),
                    "boundingBox": norm_bbox,
                    "maskDataUrl": mask_url,
                    "polygon": polygon,
                    "layer": layer_name,
                })

            # Step 5: Build spatial layers
            layers = build_spatial_layers_from_objects(objects, depth_m, w, h)

            # Step 6: Build scene graph (pure CPU, no model)
            scene_graph = build_scene_graph_from_objects(request.shotId, objects)
        except Exception as e:
            _fail("post_process", e)

        result = {
            "analysisId": analysis_id,
            "depthMapUrl": depth_url,
            "objects": objects,
            "layers": layers,
            "sceneGraph": scene_graph,
            "vlmDetectedClasses": detected_classes,
            "vlmDetectedScene": detected_scene,
        }

        # Persist all artifacts if projectId is supplied
        if request.projectId:
            _stage = "persist"
            try:
                saved_all: list[str] = []
                # depth step
                saved_all += await _save_project_artifact(
                    request.projectId, "depth", {"depth_map.png": _pil_to_png_bytes(depth_pil_resized)}
                ) or []
                # segment step (objects.json + per-object masks)
                seg_files: dict[str, bytes | dict] = {
                    "objects.json": {"objects": objects, "width": w, "height": h}
                }
                for i, (mask, _) in enumerate(masks_and_scores):
                    obj_id = objects[i]["id"]
                    seg_files[f"mask_{obj_id}.png"] = _pil_to_png_bytes(
                        Image.fromarray((mask * 255).astype(np.uint8), mode="L")
                    )
                saved_all += await _save_project_artifact(request.projectId, "segment", seg_files) or []
                # scene step
                graph_data = scene_graph.model_dump() if hasattr(scene_graph, "model_dump") else scene_graph
                saved_all += await _save_project_artifact(
                    request.projectId, "scene", {"scene_graph.json": {"shotId": request.shotId, "graph": graph_data}}
                ) or []
                # layers step
                layer_data = [l.model_dump() if hasattr(l, "model_dump") else l for l in layers]
                saved_all += await _save_project_artifact(
                    request.projectId, "layers", {"layer_assignments.json": {"width": w, "height": h, "layers": layer_data}}
                ) or []
                result["savedArtifacts"] = saved_all
            except Exception as e:
                _fail("persist", e)

        return result

    except HTTPException:
        # Re-raise HTTPExceptions raised by the per-stage handlers as-is
        # so the client sees the meaningful 503 detail.
        raise
    except Exception as e:
        # Last-resort safety net for anything not caught by the per-stage
        # handlers (e.g., an error during early request parsing).
        _log.exception("[%s] Unhandled error", analysis_id)
        raise HTTPException(
            status_code=500,
            detail=f"[{_stage}] {type(e).__name__}: {e}"[:500],
        )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/depth — Depth map only
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/depth", response_model=DepthResponse)
async def generate_depth(request: DepthRequest) -> DepthResponse:
    """Generate a depth map from an image."""
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size
        depth_norm = model_manager.depth_model.predict(image)
        model_manager.unload_depth()   # depth_norm numpy is all we need
        depth_pil = numpy_to_pil_depth(depth_norm, cmap="gray")
        depth_pil_resized = depth_pil.resize((w, h), Image.LANCZOS)

        depth_meters_arr = depth_to_meters(depth_norm, scale=50.0)

        saved_files: Optional[list[str]] = None
        # Persist if projectId supplied
        if request.projectId:
            depth_bytes = _pil_to_png_bytes(depth_pil_resized)
            saved = await _save_project_artifact(
                request.projectId, "depth", {"depth_map.png": depth_bytes}
            )
            if saved is not None:
                saved_files = saved

        return DepthResponse(
            depthMapUrl=pil_to_base64(depth_pil_resized),
            width=w,
            height=h,
            minDepth=float(depth_meters_arr.min()),
            maxDepth=float(depth_meters_arr.max()),
            savedFiles=saved_files,
        )
    except Exception as e:
        _log.exception("[depth] Error")
        raise HTTPException(status_code=500, detail="Depth estimation failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/segment — Object segmentation only
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/segment", response_model=SegmentResponse)
async def segment_objects(request: SegmentRequest) -> SegmentResponse:
    """Detect and segment objects using Grounding DINO + SAM2."""
    try:
        image = await _load_image(request.imageUrl)
        w, h = image.size
        image_np = np.array(image)

        # ── DepthAnything V2 ──────────────────────────────────────────────────
        depth_norm = model_manager.depth_model.predict(image)
        depth_m = depth_to_meters(depth_norm, scale=50.0)
        model_manager.unload_depth()   # depth_m numpy array is all we need

        # ── Qwen3-VL ──────────────────────────────────────────────────────────
        _log.info("[segment] Running VLM detection (local Qwen3-VL)...")
        import asyncio
        detected_classes, detected_scene = await asyncio.create_task(
            vlm_detect(image)
        )
        prompt = ".".join(detected_classes)
        _log.info("[segment] VLM scene='%s' classes=%s", detected_scene, detected_classes)
        model_manager.unload_qwen3vl()   # prompt string is all we need

        # ── Grounding DINO ───────────────────────────────────────────────────
        detections = model_manager.grounding_dino.detect(image, prompt=prompt, threshold=0.3)

        if not detections:
            return {"objects": []}

        boxes = np.array([d.box for d in detections])
        scores = np.array([d.score for d in detections])
        model_manager.unload_grounding_dino()   # boxes/scores numpy arrays are all we need

        # ── SAM2 ─────────────────────────────────────────────────────────────
        masks_and_scores = model_manager.sam2.predict_masks_from_boxes(image_np, boxes, scores)
        model_manager.unload_sam2()   # masks numpy arrays are all we need

        # ── CPU post-processing ───────────────────────────────────────────────
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

        result = {"objects": objects}

        # Persist if projectId supplied
        if request.projectId:
            files: dict[str, bytes | dict] = {
                "objects.json": {"objects": objects, "width": w, "height": h}
            }
            for i, (mask, _) in enumerate(masks_and_scores):
                obj_id = objects[i]["id"]
                mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
                files[f"mask_{obj_id}.png"] = _pil_to_png_bytes(mask_img)
            saved = await _save_project_artifact(request.projectId, "segment", files)
            if saved is not None:
                result["savedArtifacts"] = saved

        return result
    except Exception as e:
        _log.exception("[segment] Error")
        raise HTTPException(status_code=500, detail="Segmentation failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/layers — Build spatial layers
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/layers", response_model=LayersResponse)
async def build_layers(request: LayersRequest) -> LayersResponse:
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
        result = {"layers": layers}

        # Persist if projectId supplied
        if request.projectId:
            files: dict[str, bytes | dict] = {
                "layer_assignments.json": {
                    "width": request.imageWidth,
                    "height": request.imageHeight,
                    "layers": [l.model_dump() if hasattr(l, "model_dump") else l for l in layers],
                }
            }
            saved = await _save_project_artifact(request.projectId, "layers", files)
            if saved is not None:
                result["savedArtifacts"] = saved

        return result
    except Exception as e:
        _log.exception("[layers] Error")
        raise HTTPException(status_code=500, detail="Layer building failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/scene-graph — Build scene graph
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/scene-graph", response_model=SceneGraphResponse)
async def build_graph(request: SceneGraphRequest) -> SceneGraphResponse:
    """Build spatial relationship graph from objects."""
    try:
        graph = build_scene_graph_from_objects(request.shotId, request.objects)
        result = {"sceneGraph": graph}

        if request.projectId:
            graph_data = graph.model_dump() if hasattr(graph, "model_dump") else graph
            saved = await _save_project_artifact(
                request.projectId, "scene", {"scene_graph.json": {"shotId": request.shotId, "graph": graph_data}}
            )
            if saved is not None:
                result["savedArtifacts"] = saved

        return result
    except Exception as e:
        _log.exception("[scene-graph] Error")
        raise HTTPException(status_code=500, detail="Scene graph building failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/billboard — Generate RGBA billboard
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/billboard", response_model=BillboardResponse)
async def generate_billboard(request: BillboardRequest) -> BillboardResponse:
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
        rgba_b64 = pil_to_base64(rgba, fmt="PNG")
        result = {"rgbaUrl": rgba_b64, "billboardUrl": rgba_b64, "width": rgba.size[0], "height": rgba.size[1]}

        if request.projectId:
            safe_id = _sanitize_filename(request.objectId)
            saved = await _save_project_artifact(
                request.projectId, "billboards", {f"billboard_{safe_id}.png": _pil_to_png_bytes(rgba)}
            )
            if saved is not None:
                result["savedArtifacts"] = saved

        return result
    except Exception as e:
        _log.exception(f"[billboard] ERROR objectId=%s: %s", request.objectId, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/multiface — Generate 6-face textures
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/multiface", response_model=MultifaceResponse)
async def generate_multiface(request: MultifaceRequest) -> MultifaceResponse:
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
        result = {"faces": faces}

        if request.projectId:
            safe_id = _sanitize_filename(request.objectId)
            files: dict[str, bytes | dict] = {}
            face_pils = {
                "front": cropped,
                "back": flip_image(cropped, "horizontal"),
                "left": rotate_image_90(cropped, -1),
                "right": rotate_image_90(cropped, 1),
                "top": cropped.crop((0, 0, cropped.width, max(1, cropped.height // 4))),
                "bottom": cropped.crop((0, max(0, cropped.height - cropped.height // 4), cropped.width, cropped.height)),
            }
            for face_name, face_pil in face_pils.items():
                files[f"{safe_id}_face_{face_name}.png"] = _pil_to_png_bytes(face_pil)
            saved = await _save_project_artifact(request.projectId, "multiface", files)
            if saved is not None:
                result["savedArtifacts"] = saved

        return result
    except Exception as e:
        _log.exception("[multiface] Error")
        raise HTTPException(status_code=500, detail="Multiface generation failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/inpaint — Inpaint with wanx2.1-imageedit
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/inpaint", response_model=InpaintResponse)
async def inpaint_image(request: InpaintRequest) -> InpaintResponse:
    """
    Inpaint masked areas using local LaMa model (replaces DashScope wanx2.1-imageedit).

    maskDataUrl should be an RGBA PNG where:
      - White (alpha=255): areas to inpaint
      - Black (alpha=0):   areas to keep unchanged
    """
    try:
        base_image = load_image_from_url_or_base64(request.imageUrl)
        mask_image = load_image_from_url_or_base64(request.maskDataUrl, keep_alpha=True)

        if base_image.size != mask_image.size:
            raise HTTPException(
                status_code=400,
                detail=f"Size mismatch: base_image={base_image.size}, mask={mask_image.size}. "
                       "Mask must have the same dimensions as the base image.",
            )

        warnings: list[dict] = []

        # ── prompt 强度诊断 ───────────────────────────────────────────────────
        weak = detect_weak_prompt(request.prompt)
        if weak is not None:
            warnings.append(weak)

        # ── mask 比例诊断 ─────────────────────────────────────────────────────
        white_ratio = compute_mask_white_ratio(mask_image)
        if white_ratio < 0.05:
            warnings.append({
                "code": "small_mask",
                "reason": (
                    f"Mask covers only {white_ratio*100:.2f}% of the image. "
                    "With a small mask, the model may produce results similar to the original."
                ),
                "suggested": "Expand the mask to at least 30% of the image for better results.",
                "data": {"white_ratio": white_ratio},
            })

        result_img = generate_inpaint(
            base_image=base_image,
            mask_image=mask_image,
            prompt=request.prompt,
        )

        # Unload LaMa immediately after inference — result_img is all we need
        model_manager.unload_lama()

        result_url = pil_to_base64(result_img)
        result = {
            "inpaintResultUrl": result_url,
            "imageUrl": result_url,
            "width": result_img.size[0],
            "height": result_img.size[1],
            "model": "LaMa (local)",
            "maskWhiteRatio": white_ratio,
        }
        if warnings:
            result["warnings"] = warnings

        if request.projectId:
            from datetime import datetime as _dt
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            saved = await _save_project_artifact(
                request.projectId, "inpaint", {f"inpaint_{ts}.png": _pil_to_png_bytes(result_img)}
            )
            if saved is not None:
                result["savedArtifacts"] = saved
                result["savedFiles"] = saved

        return result

    except HTTPException:
        raise
    except Exception as e:
        _log.exception("[inpaint] Error")
        raise HTTPException(status_code=500, detail="Inpainting failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/occlusion-holes — Auto occlusion hole masks for LaMa
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/occlusion-holes", response_model=OcclusionHolesResponse)
async def occlusion_holes(request: OcclusionHolesRequest) -> OcclusionHolesResponse:
    """
    从 Analyze 物体列表自动生成遮挡空洞 mask（不跑 LaMa）。

    peel: 空洞 = 目标物体完整 SAM mask（适合逐层剥离）。
    occluded_interior: 空洞 = 目标 ∩ 更近遮挡物；无重叠时回退 peel。
    """
    mode = (request.mode or "peel").strip().lower()
    if mode not in ("peel", "occluded_interior"):
        raise HTTPException(status_code=400, detail="mode must be 'peel' or 'occluded_interior'")

    try:
        from app.services.occlusion_holes import (
            compute_occlusion_holes,
            holes_to_dicts,
            merge_hole_masks,
        )

        holes = compute_occlusion_holes(
            request.objects,
            image_width=request.imageWidth,
            image_height=request.imageHeight,
            target_object_ids=request.targetObjectIds,
            mode=mode,  # type: ignore[arg-type]
        )
        merged = merge_hole_masks(holes, (request.imageWidth, request.imageHeight))
        return OcclusionHolesResponse(
            holes=holes_to_dicts(holes),
            mergedMaskDataUrl=merged,
            mode=mode,
            count=len(holes),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        _log.exception("[occlusion-holes] Error")
        raise HTTPException(status_code=500, detail="Occlusion hole detection failed")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/paper-style — Paper illustration style transfer
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/paper-style", response_model=PaperStyleResponse)
async def paper_style_transfer(request: PaperStyleRequest) -> PaperStyleResponse:
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
        result = {"styledImageUrl": pil_to_base64(styled, fmt="PNG")}

        if request.projectId:
            key = _sanitize_filename(getattr(request, "layerKey", None) or "default")
            saved = await _save_project_artifact(
                request.projectId, "paper", {f"paper_style_{key}.png": _pil_to_png_bytes(styled)}
            )
            if saved is not None:
                result["savedArtifacts"] = saved

        return result
    except Exception as e:
        _log.exception("[paper-style] Error")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/paper-diorama — Full diorama texture set for one object
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/paper-diorama", response_model=PaperDioramaResponse)
async def paper_diorama_generate(request: PaperDioramaRequest) -> PaperDioramaResponse:
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

        # Normalise keys from snake_case (paper_diorama output) to camelCase (Pydantic v2 response model)
        textures = {
            "paperStyleUrl": textures.get("paper_style_url"),
            "normalMapUrl": textures.get("normal_map_url"),
            "thicknessGrayUrl": textures.get("thickness_gray_url"),
            "outlinedUrl": textures.get("outlined_url"),
            "width": image.width,
            "height": image.height,
        }

        # Persist if projectId supplied — save the 5 texture PNGs
        if request.projectId:
            # objectId not in PaperDioramaRequest — derive from a hash of the mask
            import hashlib as _hl
            obj_id = _hl.md5(mask.tobytes()).hexdigest()[:10]
            safe_id = _sanitize_filename(obj_id)
            files: dict[str, bytes | dict] = {}
            for kind, url in textures.items():
                if not isinstance(url, str) or not url.startswith("data:"):
                    continue
                try:
                    b64 = url.split(",", 1)[1]
                    files[f"{kind}_{safe_id}.png"] = base64.b64decode(b64)
                except Exception:
                    continue
            if files:
                saved = await _save_project_artifact(request.projectId, "paper", files)
                if saved is not None:
                    textures["savedFiles"] = saved

        return textures
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("[paper-diorama] Error")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/aicss/paper-layer — Paper diorama texture for a depth layer
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/paper-layer", response_model=PaperLayerResponse)
async def paper_layer_generate(request: PaperLayerRequest) -> PaperLayerResponse:
    """
    Generate paper-diorama texture for a full depth layer image.
    Returns the same texture fields as /paper-diorama.
    """
    try:
        image = await _load_image(request.layerImageUrl)

        # ── Mask extraction ────────────────────────────────────────────────────
        # Depth-split layers are RGBA PNGs where alpha=255 means "this pixel
        # belongs to this layer" and alpha=0 means "empty / other layer".
        # We always extract the mask from the image's own alpha channel.
        # request.layerMaskUrl is ignored for depth layers — the alpha channel
        # is the authoritative mask and already matches the split boundaries.
        image_rgba = image.convert("RGBA")
        alpha = np.array(image_rgba.split()[-1])  # last channel = alpha

        if request.layerMaskUrl:
            # External mask is supported for object-level paper dioramas,
            # but depth layers should always prefer their intrinsic alpha.
            external = np.array(base64_to_pil(request.layerMaskUrl).convert("L"))
            if external.shape == alpha.shape:
                # Intersect: only pixels that are in BOTH the external mask
                # AND the depth layer are treated as paper (AND gives cleaner
                # boundaries for objects that were manually assigned).
                alpha = np.minimum(alpha, external)
            # If sizes differ, fall through — alpha is still used as primary.

        mask = alpha
        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        # Ensure image and mask are the same size
        if image.size != mask.shape[::-1]:
            image = image.resize((mask.shape[1], mask.shape[0]), Image.LANCZOS)
            image_rgba = image.convert("RGBA")

        from app.utils.paper_diorama import generate_paper_diorama_textures
        textures = generate_paper_diorama_textures(
            image=image,
            mask=mask,
            thickness_range_mm=(request.thicknessMin, request.thicknessMax),
            outline_width=request.outlineWidth,
            color_levels=request.colorLevels,
            style_strength=request.styleStrength,
        )

        # Normalise keys from snake_case (paper_diorama output) to camelCase (Pydantic v2 response model)
        textures = {
            "paperStyleUrl": textures.get("paper_style_url"),
            "normalMapUrl": textures.get("normal_map_url"),
            "thicknessGrayUrl": textures.get("thickness_gray_url"),
            "outlinedUrl": textures.get("outlined_url"),
            "width": image.width,
            "height": image.height,
            "layerKey": request.layerKey,
        }

        # Persist if projectId supplied — 5 textures named by layerKey
        if request.projectId:
            key = _sanitize_filename(request.layerKey or "default")
            files: dict[str, bytes] = {}
            for kind, url in textures.items():
                if not isinstance(url, str) or not url.startswith("data:"):
                    continue
                try:
                    b64 = url.split(",", 1)[1]
                    safe_kind = kind.replace("Url", "").replace("Gray", "Gray")
                    files[f"{safe_kind}_{key}.png"] = base64.b64decode(b64)
                except Exception:
                    continue
            if files:
                saved = await _save_project_artifact(request.projectId, "paper", files)
                if saved is not None:
                    textures["savedFiles"] = saved

        return textures
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("[paper-layer] Error")
        raise HTTPException(status_code=500, detail="Paper layer generation failed")
