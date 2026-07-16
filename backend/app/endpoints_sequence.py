"""
v2 API - Sequence Analysis Endpoints.

Manages multi-frame sequence processing for shot analysis:
  POST /api/aicss/v2/sequences                — Analyze an image sequence
  POST /api/aicss/v2/sequences/from-script    — Analyze from script scenes
  GET  /api/aicss/v2/sequences/{id}           — Get sequence details
  GET  /api/aicss/v2/sequences/{id}/scene-links — Get scene association graph
  GET  /api/aicss/v2/sequences/{id}/objects/{globalId} — Get cross-frame object detail

Reference: docs/API_PROTOCOL_v2.md Section 6
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.project_store import project_store

_log_router = __import__("logging").getLogger("aicss")

router = APIRouter()

# ─── In-memory sequence store (production: use Redis / DB) ──────────────────────

_sequence_store: dict[str, dict] = {}

# ─── Shared type aliases ────────────────────────────────────────────────────────

TrackingMode = Literal["vlm", "semantic", "iou", "hybrid"]
FrameType = Literal[
    "wide_shot", "medium_shot", "close_up",
    "extreme_close_up", "over_shoulder", "pov", "establishing",
]
SceneLinkType = Literal["same_scene", "same_character", "continuity", "contrast"]
DepthLayerKey = Literal["foreground", "midground", "background", "sky"]


# ─── Request Models ─────────────────────────────────────────────────────────────

class AnalyzeSequenceRequest(BaseModel):
    """Analyze an image sequence (multiple frames from the same shot)."""
    shotId: str = Field(..., description="Shot ID")
    frameIds: list[str] = Field(..., description="Frame IDs in order")
    imageUrls: list[str] = Field(..., description="Image URLs corresponding to each frame")
    projectId: Optional[str] = Field(None, description="Optional project ID for persistence")
    enableTracking: bool = Field(True, description="Enable cross-frame object tracking")
    trackingMode: TrackingMode = Field("vlm", description="Tracking mode")
    frameTypes: Optional[list[FrameType]] = Field(
        None, description="Optional per-frame types (same length as frameIds)"
    )
    frameDescriptions: Optional[list[str]] = Field(
        None, description="Optional per-frame descriptions"
    )
    matchingThreshold: float = Field(0.6, ge=0.0, le=1.0, description="Matching threshold")
    maxCandidatesPerObject: int = Field(5, ge=1, le=50, description="Max tracking candidates")


class ScriptScene(BaseModel):
    """A scene extracted from a script, used by from-script endpoint."""
    sceneId: str
    frameId: str
    imageUrl: str
    sceneType: Optional[FrameType] = None
    description: Optional[str] = None
    characters: Optional[list[str]] = None
    location: Optional[str] = None
    timeOfDay: Optional[str] = None


class AnalyzeFromScriptRequest(BaseModel):
    """Analyze frames defined by script scenes."""
    shotId: str
    scenes: list[ScriptScene]
    projectId: Optional[str] = None
    enableTracking: bool = True
    trackingMode: TrackingMode = "vlm"


# ─── Response Models ────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x: float
    y: float
    w: float
    h: float


class ObjectAppearance(BaseModel):
    frameId: str
    frameIndex: int
    localId: str
    bbox: BoundingBox
    depth: float
    matchConfidence: float


class CrossFrameObject(BaseModel):
    globalId: str
    classLabel: str
    appearances: list[ObjectAppearance]


class SceneLink(BaseModel):
    sourceFrameId: str
    targetFrameId: str
    linkType: SceneLinkType
    confidence: float


class FrameResult(BaseModel):
    frameId: str
    frameIndex: int
    frameType: Optional[FrameType] = None
    depthMapUrl: str
    objects: list[dict]
    layers: list[dict]
    globalObjectIds: dict[str, str]  # local_id -> global_id
    vlmScene: Optional[str] = None
    vlmClasses: Optional[list[str]] = None


class SequenceMetadata(BaseModel):
    totalProcessingTimeMs: int
    framesProcessed: int
    framesFailed: int
    objectsTracked: int
    trackingMode: TrackingMode


class SequenceResult(BaseModel):
    sequenceId: str
    shotId: str
    projectId: Optional[str] = None
    createdAt: str
    frameCount: int
    frames: list[FrameResult]
    sceneLinks: list[SceneLink]
    crossFrameObjects: list[CrossFrameObject]
    metadata: SequenceMetadata


class FrameLink(BaseModel):
    sourceFrameId: str
    targetFrameId: str
    linkType: SceneLinkType
    confidence: float
    sharedObjects: Optional[list[str]] = None
    sharedClasses: Optional[list[str]] = None


class SceneLinksResponse(BaseModel):
    sequenceId: str
    shotId: str
    frameLinks: list[FrameLink]
    crossFrameObjects: list[CrossFrameObject]
    statistics: dict


class ObjectAppearanceDetail(BaseModel):
    frameId: str
    frameIndex: int
    localId: str
    bbox: BoundingBox
    depth: float
    matchConfidence: float
    layer: Optional[DepthLayerKey] = None


class TrajectoryPoint(BaseModel):
    frameId: str
    x: float
    y: float
    depth: float


class CrossFrameObjectDetail(BaseModel):
    globalId: str
    classLabel: str
    totalAppearances: int
    appearances: list[ObjectAppearanceDetail]
    trajectory: dict
    layerHistory: list[dict]


# ─── TemporalTracker ───────────────────────────────────────────────────────────

class TemporalTracker:
    """
    Tracks objects across frames based on class label matching and bounding-box IoU.

    Modes:
      - vlm:      uses VLM-detected classes (default)
      - semantic: label similarity only
      - iou:      IoU overlap only
      - hybrid:   combines both
    """

    def __init__(
        self,
        mode: TrackingMode = "vlm",
        matching_threshold: float = 0.6,
        max_candidates: int = 5,
    ):
        self.mode = mode
        self.matching_threshold = matching_threshold
        self.max_candidates = max_candidates
        self.global_counter: int = 0
        self.global_objects: dict[str, dict] = {}  # global_id -> obj

    def _next_global_id(self) -> str:
        self.global_counter += 1
        return f"gobj_{self.global_counter:04d}"

    @staticmethod
    def _bbox_iou(a: dict, b: dict) -> float:
        """Compute IoU between two normalised bounding boxes."""
        ax, ay, aw, ah = a["x"], a["y"], a["w"], a["h"]
        bx, by, bw, bh = b["x"], b["y"], b["w"], b["h"]

        xi = max(ax, bx)
        yi = max(ay, by)
        wi = min(ax + aw, bx + bw) - xi
        hi = min(ay + ah, by + bh) - yi

        if wi <= 0 or hi <= 0:
            return 0.0
        inter = wi * hi
        union = aw * ah + bw * bh - inter
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _class_score(label_a: str, label_b: str) -> float:
        """Simple label similarity: 1.0 if exact match, 0.0 otherwise."""
        return 1.0 if label_a.lower() == label_b.lower() else 0.0

    def track_frame(
        self,
        frame_index: int,
        frame_id: str,
        objects: list[dict],
    ) -> dict[str, str]:
        """
        Match current-frame objects against known global objects.
        Returns dict: {local_id -> global_id}
        """
        local_to_global: dict[str, str] = {}

        if not self.global_objects:
            # First frame: assign new global IDs
            for obj in objects:
                gid = self._next_global_id()
                local_to_global[obj["id"]] = gid
                self.global_objects[gid] = {
                    "globalId": gid,
                    "classLabel": obj["classLabel"],
                    "appearances": [
                        {
                            "frameId": frame_id,
                            "frameIndex": frame_index,
                            "localId": obj["id"],
                            "bbox": obj["boundingBox"],
                            "depth": obj["depth"],
                            "matchConfidence": 1.0,
                        }
                    ],
                }
            return local_to_global

        # Subsequent frames: match against existing global objects
        for obj in objects:
            candidates: list[tuple[str, float]] = []  # (global_id, score)

            for gid, g_obj in self.global_objects.items():
                score = 0.0

                if self.mode in ("vlm", "semantic", "hybrid"):
                    score += self._class_score(g_obj["classLabel"], obj["classLabel"])

                if self.mode in ("iou", "hybrid"):
                    iou = self._bbox_iou(g_obj["appearances"][-1]["bbox"], obj["boundingBox"])
                    score += iou

                if self.mode == "hybrid":
                    score /= 2

                if score >= self.matching_threshold:
                    candidates.append((gid, score))

            # Pick best candidate
            candidates.sort(key=lambda x: x[1], reverse=True)
            if candidates:
                best_gid, best_score = candidates[0]
            else:
                best_gid = self._next_global_id()
                best_score = 1.0  # new object gets full confidence

            local_to_global[obj["id"]] = best_gid

            if best_gid not in self.global_objects:
                self.global_objects[best_gid] = {
                    "globalId": best_gid,
                    "classLabel": obj["classLabel"],
                    "appearances": [],
                }

            self.global_objects[best_gid]["appearances"].append({
                "frameId": frame_id,
                "frameIndex": frame_index,
                "localId": obj["id"],
                "bbox": obj["boundingBox"],
                "depth": obj["depth"],
                "matchConfidence": best_score,
            })

        return local_to_global

    def build_scene_links(
        self,
        frames: list[FrameResult],
    ) -> list[SceneLink]:
        """
        Discover scene-level links between adjacent frames based on shared objects.
        """
        links: list[SceneLink] = []

        for i in range(len(frames) - 1):
            src = frames[i]
            tgt = frames[i + 1]

            shared_ids = set(src.globalObjectIds.values()) & set(tgt.globalObjectIds.values())
            shared_classes = set()
            for obj in src.objects:
                if src.globalObjectIds.get(obj["id"]) in shared_ids:
                    shared_classes.add(obj["classLabel"])

            if not shared_ids:
                link_type: SceneLinkType = "contrast"
                confidence = 0.0
            elif len(shared_classes) == 1:
                link_type = "same_character"
                confidence = len(shared_ids) / max(len(src.objects), 1)
            else:
                link_type = "continuity"
                confidence = len(shared_ids) / max(len(src.objects), 1)

            links.append(SceneLink(
                sourceFrameId=src.frameId,
                targetFrameId=tgt.frameId,
                linkType=link_type,
                confidence=round(confidence, 3),
            ))

        return links

    def get_cross_frame_objects(self) -> list[CrossFrameObject]:
        return [
            CrossFrameObject(
                globalId=gid,
                classLabel=g_obj["classLabel"],
                appearances=[
                    ObjectAppearance(**app) for app in g_obj["appearances"]
                ],
            )
            for gid, g_obj in self.global_objects.items()
        ]


# ─── Per-frame analysis (reuses v1 logic) ──────────────────────────────────────

async def _analyze_single_frame(
    image_url: str,
    shot_id: str,
    project_id: Optional[str] = None,
) -> dict:
    """
    Run a single frame through the v1 /analyze pipeline.
    Delegates to the existing endpoints.analyze() implementation.
    """
    from app.endpoints import analyze, AnalyzeRequest
    request = AnalyzeRequest(
        imageUrl=image_url,
        shotId=shot_id,
        projectId=project_id,
    )
    return await analyze(request)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/v2/sequences", response_model=SequenceResult)
async def analyze_sequence(request: AnalyzeSequenceRequest):
    """
    Analyze an image sequence.

    Processing pipeline:
      1. Validate request (frameIds and imageUrls must have the same length)
      2. For each frame, call _analyze_single_frame
      3. Use TemporalTracker for cross-frame object matching
      4. Build scene links
      5. Persist to project_store if projectId provided
      6. Return SequenceResult
    """
    if len(request.frameIds) != len(request.imageUrls):
        raise HTTPException(
            status_code=400,
            detail="frameIds and imageUrls must have the same length",
        )

    if not request.frameIds:
        raise HTTPException(
            status_code=400,
            detail="frameIds cannot be empty",
        )

    sequence_id = f"seq_{uuid.uuid4().hex[:8]}"
    start_time = time.time()
    tracker = TemporalTracker(
        mode=request.trackingMode,
        matching_threshold=request.matchingThreshold,
        max_candidates=request.maxCandidatesPerObject,
    )

    frames: list[FrameResult] = []
    frames_failed = 0

    for idx, (frame_id, image_url) in enumerate(zip(request.frameIds, request.imageUrls)):
        try:
            result = await _analyze_single_frame(
                image_url=image_url,
                shot_id=request.shotId,
                project_id=request.projectId,
            )

            objects = result.get("objects", [])
            layers = result.get("layers", [])

            # Cross-frame tracking
            global_ids: dict[str, str] = {}
            if request.enableTracking:
                global_ids = tracker.track_frame(idx, frame_id, objects)

            frame_type = None
            if request.frameTypes and idx < len(request.frameTypes):
                frame_type = request.frameTypes[idx]

            frames.append(FrameResult(
                frameId=frame_id,
                frameIndex=idx,
                frameType=frame_type,
                depthMapUrl=result.get("depthMapUrl", ""),
                objects=objects,
                layers=layers,
                globalObjectIds=global_ids,
                vlmScene=result.get("vlmDetectedScene"),
                vlmClasses=result.get("vlmDetectedClasses"),
            ))

        except Exception as e:
            _log_router.warning(f"[sequence] Frame {frame_id} failed: {e}")
            frames_failed += 1
            frames.append(FrameResult(
                frameId=frame_id,
                frameIndex=idx,
                frameType=request.frameTypes[idx] if request.frameTypes and idx < len(request.frameTypes) else None,
                depthMapUrl="",
                objects=[],
                layers=[],
                globalObjectIds={},
            ))

    # Build scene links
    scene_links = tracker.build_scene_links(frames) if request.enableTracking else []
    cross_frame_objects = tracker.get_cross_frame_objects() if request.enableTracking else []

    total_time_ms = int((time.time() - start_time) * 1000)

    result = SequenceResult(
        sequenceId=sequence_id,
        shotId=request.shotId,
        projectId=request.projectId,
        createdAt=datetime.now(timezone.utc).isoformat(),
        frameCount=len(frames),
        frames=frames,
        sceneLinks=scene_links,
        crossFrameObjects=cross_frame_objects,
        metadata=SequenceMetadata(
            totalProcessingTimeMs=total_time_ms,
            framesProcessed=len(frames) - frames_failed,
            framesFailed=frames_failed,
            objectsTracked=len(cross_frame_objects),
            trackingMode=request.trackingMode,
        ),
    )

    # Persist to project_store if projectId provided
    if request.projectId:
        try:
            seq_data = result.model_dump() if hasattr(result, "model_dump") else result
            await project_store.save_sequence(
                request.projectId,
                seq_data,
            )
        except Exception as e:
            _log_router.warning(f"[sequence] Failed to persist sequence: {e}")

    # Cache in memory for later queries
    _sequence_store[sequence_id] = result.model_dump() if hasattr(result, "model_dump") else result

    return result


@router.post("/v2/sequences/from-script", response_model=SequenceResult)
async def analyze_from_script(request: AnalyzeFromScriptRequest):
    """
    Analyze frames defined by script scenes.
    Converts ScriptScene items to the format expected by analyze_sequence.
    """
    if not request.scenes:
        raise HTTPException(
            status_code=400,
            detail="scenes cannot be empty",
        )

    frame_ids = [s.frameId for s in request.scenes]
    image_urls = [s.imageUrl for s in request.scenes]
    frame_types = [s.sceneType for s in request.scenes if s.sceneType is not None]

    seq_request = AnalyzeSequenceRequest(
        shotId=request.shotId,
        frameIds=frame_ids,
        imageUrls=image_urls,
        projectId=request.projectId,
        enableTracking=request.enableTracking,
        trackingMode=request.trackingMode,
        frameTypes=frame_types if len(frame_types) == len(frame_ids) else None,
    )

    return await analyze_sequence(seq_request)


@router.get("/v2/sequences/{sequence_id}", response_model=SequenceResult)
async def get_sequence(sequence_id: str):
    """Get sequence details by ID."""
    seq_data = _sequence_store.get(sequence_id)
    if seq_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sequence not found: {sequence_id}",
        )
    return seq_data


@router.get("/v2/sequences/{sequence_id}/scene-links", response_model=SceneLinksResponse)
async def get_scene_links(sequence_id: str):
    """
    Get the scene association graph for a sequence.
    Returns FrameLink list with shared objects and statistics.
    """
    seq_data = _sequence_store.get(sequence_id)
    if seq_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sequence not found: {sequence_id}",
        )

    scene_links = seq_data.get("sceneLinks", [])
    cross_frame_objects = seq_data.get("crossFrameObjects", [])

    # Build FrameLink with shared object details
    frame_links: list[FrameLink] = []
    links_by_type: dict[str, int] = {}

    for link in scene_links:
        link_type: SceneLinkType = link.get("linkType", "continuity")
        links_by_type[link_type] = links_by_type.get(link_type, 0) + 1

        # Find shared objects between linked frames
        frames_map = {f["frameId"]: f for f in seq_data.get("frames", [])}
        src_frame = frames_map.get(link.get("sourceFrameId", ""))
        tgt_frame = frames_map.get(link.get("targetFrameId", ""))

        shared_objects: list[str] = []
        shared_classes: list[str] = []

        if src_frame and tgt_frame:
            shared_global = set(src_frame.get("globalObjectIds", {}).values()) & set(
                tgt_frame.get("globalObjectIds", {}).values()
            )
            for gobj in cross_frame_objects:
                if gobj.get("globalId") in shared_global:
                    shared_objects.append(gobj.get("globalId", ""))
                    shared_classes.append(gobj.get("classLabel", ""))

        frame_links.append(FrameLink(
            sourceFrameId=link.get("sourceFrameId", ""),
            targetFrameId=link.get("targetFrameId", ""),
            linkType=link_type,
            confidence=link.get("confidence", 0.0),
            sharedObjects=shared_objects if shared_objects else None,
            sharedClasses=shared_classes if shared_classes else None,
        ))

    total_appearances = sum(
        len(gobj.get("appearances", [])) for gobj in cross_frame_objects
    )
    avg_appearances = (
        total_appearances / len(cross_frame_objects)
        if cross_frame_objects else 0.0
    )

    return SceneLinksResponse(
        sequenceId=sequence_id,
        shotId=seq_data.get("shotId", ""),
        frameLinks=frame_links,
        crossFrameObjects=[
            CrossFrameObject(**gobj) for gobj in cross_frame_objects
        ],
        statistics={
            "totalLinks": len(frame_links),
            "linksByType": links_by_type,
            "uniqueObjects": len(cross_frame_objects),
            "averageAppearancesPerObject": round(avg_appearances, 2),
        },
    )


@router.get(
    "/v2/sequences/{sequence_id}/objects/{global_id}",
    response_model=CrossFrameObjectDetail,
)
async def get_cross_frame_object(sequence_id: str, global_id: str):
    """
    Get detailed information about a cross-frame object.
    Includes trajectory and layer history.
    """
    seq_data = _sequence_store.get(sequence_id)
    if seq_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sequence not found: {sequence_id}",
        )

    cross_frame_objects = seq_data.get("crossFrameObjects", [])
    target_obj = next(
        (gobj for gobj in cross_frame_objects if gobj.get("globalId") == global_id),
        None,
    )
    if target_obj is None:
        raise HTTPException(
            status_code=404,
            detail=f"Object not found: {global_id}",
        )

    appearances = target_obj.get("appearances", [])
    frames_map = {f["frameId"]: f for f in seq_data.get("frames", [])}

    # Build appearance details with layer info
    appearance_details: list[ObjectAppearanceDetail] = []
    trajectory: list[TrajectoryPoint] = []
    layer_history: list[dict] = []

    for app in appearances:
        frame = frames_map.get(app.get("frameId", ""))
        layer = None
        if frame:
            for obj in frame.get("objects", []):
                if obj.get("id") == app.get("localId"):
                    layer = obj.get("layer")
                    break

        appearance_details.append(ObjectAppearanceDetail(
            frameId=app.get("frameId", ""),
            frameIndex=app.get("frameIndex", 0),
            localId=app.get("localId", ""),
            bbox=BoundingBox(**app.get("bbox", {})),
            depth=app.get("depth", 0.0),
            matchConfidence=app.get("matchConfidence", 0.0),
            layer=layer,
        ))

        bbox = app.get("bbox", {})
        trajectory.append(TrajectoryPoint(
            frameId=app.get("frameId", ""),
            x=bbox.get("x", 0.0) + bbox.get("w", 0.0) / 2,
            y=bbox.get("y", 0.0) + bbox.get("h", 0.0) / 2,
            depth=app.get("depth", 0.0),
        ))
        layer_history.append({
            "frameId": app.get("frameId", ""),
            "layer": layer,
        })

    # Compute motion pattern from trajectory
    depths = [p.depth for p in trajectory]
    depth_range: tuple[float, float] = (min(depths), max(depths)) if depths else (0.0, 0.0)

    x_vals = [p.x for p in trajectory]
    motion_range = max(x_vals) - min(x_vals) if len(x_vals) > 1 else 0.0

    if motion_range < 0.05:
        motion_pattern = "static"
    elif motion_range < 0.15:
        motion_pattern = "slow"
    elif motion_range < 0.3:
        motion_pattern = "medium"
    elif motion_range < 0.5:
        motion_pattern = "fast"
    else:
        motion_pattern = "erratic"

    return CrossFrameObjectDetail(
        globalId=global_id,
        classLabel=target_obj.get("classLabel", ""),
        totalAppearances=len(appearances),
        appearances=appearance_details,
        trajectory={
            "positions": [p.model_dump() if hasattr(p, "model_dump") else p for p in trajectory],
            "depthRange": list(depth_range),
            "motionPattern": motion_pattern,
        },
        layerHistory=layer_history,
    )
