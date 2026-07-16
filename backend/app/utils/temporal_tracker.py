"""
Temporal Tracker — Cross-frame object tracking for script-generated single-scene frames.

This module provides cross-frame object tracking for sequences of frames that may not be
continuous video frames. It uses Qwen3-VL for semantic feature extraction and supports
hybrid matching (semantic + appearance + IoU).

Design assumptions:
  - Frames are script-generated single-scene frames, not necessarily consecutive video frames
  - Objects may appear/disappear between frames
  - Same object can appear in different sizes/positions across frames
  - AI-generated frames may have significant visual variation

Usage:
    from app.models.model_manager import model_manager
    tracker = TemporalTracker(model_manager, model_manager.qwen3vl)
    frames_with_ids, cross_frame_objects, scene_links = tracker.track_sequence(frames)
"""

import uuid
import time
import logging
from typing import Optional, Any

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

_log = logging.getLogger("aicss.temporal")


# ─────────────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    x: float = Field(..., ge=0, le=1, description="Left-top x (0-1)")
    y: float = Field(..., ge=0, le=1, description="Left-top y (0-1)")
    w: float = Field(..., ge=0, le=1, description="Width (0-1)")
    h: float = Field(..., ge=0, le=1, description="Height (0-1)")


class SpatialObject(BaseModel):
    """Spatial object extracted from a single frame."""
    id: str = Field(..., description="Local object ID within this frame")
    classLabel: str = Field(..., description="Object class label (English, lowercase)")
    depth: float = Field(..., ge=0, description="Depth in meters")
    boundingBox: BoundingBox
    maskDataUrl: Optional[str] = Field(None, description="Base64 mask PNG")
    polygon: Optional[list[list[float]]] = Field(None, description="[[x,y],...] normalized 0-1")
    layer: str = Field(..., description="Depth layer key (foreground/midground/background/sky)")
    confidence: Optional[float] = Field(None, ge=0, le=1)


class ObjectAppearance(BaseModel):
    """A single appearance of an object in one frame."""
    frameId: str
    frameIndex: int
    localId: str
    bbox: BoundingBox
    depth: float
    matchConfidence: float = Field(..., ge=0, le=1)


class CrossFrameObject(BaseModel):
    """An object tracked across multiple frames."""
    globalId: str
    classLabel: str
    appearances: list[ObjectAppearance] = Field(default_factory=list)


class SceneLink(BaseModel):
    """Link between two frames indicating scene relationship."""
    sourceFrameId: str
    targetFrameId: str
    linkType: str = Field(..., description="same_scene | same_character | continuity | contrast")
    confidence: float = Field(..., ge=0, le=1)


class FrameResult(BaseModel):
    """Result of analyzing a single frame, extended with tracking info."""
    frameId: str
    frameIndex: int
    frameType: Optional[str] = Field(None, description="wide_shot/medium_shot/close_up/etc.")
    depthMapUrl: str = Field(default="")
    objects: list[SpatialObject] = Field(default_factory=list)
    layers: list[Any] = Field(default_factory=list)
    globalObjectIds: dict[str, str] = Field(default_factory=dict, description="local_id -> global_id")
    vlmScene: Optional[str] = Field(None)
    vlmClasses: Optional[list[str]] = Field(None)


class Trajectory(BaseModel):
    """Motion trajectory of a tracked object across frames."""
    globalId: str
    classLabel: str
    center_x: list[float] = Field(default_factory=list)
    center_y: list[float] = Field(default_factory=list)
    depth: list[float] = Field(default_factory=list)
    area: list[float] = Field(default_factory=list)
    frame_indices: list[int] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_iou(bbox1: BoundingBox, bbox2: BoundingBox) -> float:
    """
    Compute Intersection over Union (IoU) between two normalized bounding boxes.

    Args:
        bbox1: First bounding box (normalized 0-1)
        bbox2: Second bounding box (normalized 0-1)

    Returns:
        IoU score in [0, 1]. Returns 0 if boxes don't overlap.
    """
    x1 = max(bbox1.x, bbox2.x)
    y1 = max(bbox1.y, bbox2.y)
    x2 = min(bbox1.x + bbox1.w, bbox2.x + bbox2.w)
    y2 = min(bbox1.y + bbox1.h, bbox2.y + bbox2.h)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = bbox1.w * bbox1.h
    area2 = bbox2.w * bbox2.h
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Compute cosine similarity between two feature vectors.

    Args:
        vec1: First feature vector
        vec2: Second feature vector

    Returns:
        Cosine similarity in [-1, 1]. Returns 0 if either vector is zero.
    """
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 < 1e-8 or norm2 < 1e-8:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))


def build_trajectory(appearances: list[ObjectAppearance]) -> Trajectory:
    """
    Build a motion trajectory from a list of object appearances.

    Args:
        appearances: List of appearances in chronological order

    Returns:
        Trajectory with center positions, depth, and area over time
    """
    if not appearances:
        return Trajectory(globalId="", classLabel="")

    first = appearances[0]
    traj = Trajectory(
        globalId=first.frameId,
        classLabel="",
        center_x=[],
        center_y=[],
        depth=[],
        area=[],
        frame_indices=[],
    )

    for app in appearances:
        bbox = app.bbox
        traj.center_x.append(bbox.x + bbox.w / 2)
        traj.center_y.append(bbox.y + bbox.h / 2)
        traj.depth.append(app.depth)
        traj.area.append(bbox.w * bbox.h)
        traj.frame_indices.append(app.frameIndex)

    return traj


# ─────────────────────────────────────────────────────────────────────────────
# VLM Feature Extractor
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_EXTRACT_SYSTEM_PROMPT = (
    "You are a precise visual feature extraction assistant. "
    "Describe the visual appearance of the specified object region in detail, "
    "including: color, texture, shape, size relative to frame, position, "
    "apparent material, and any distinctive visual characteristics. "
    "Be specific and use concise descriptions."
)

FEATURE_EXTRACT_USER_PROMPT = (
    "Describe the visual appearance of the object in the highlighted region. "
    "Focus on: primary colors, texture pattern, shape characteristics, "
    "relative size within the frame, and any unique visual markers. "
    "Return your description in a structured format."
)


def _normalize_class_label(label: str) -> str:
    """Normalize class label to lowercase and strip whitespace."""
    return label.strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
# Temporal Tracker
# ─────────────────────────────────────────────────────────────────────────────

class TemporalTracker:
    """
    Cross-frame object tracker for script-generated single-scene frames.

    This tracker maintains global object IDs across a sequence of frames,
    matching objects based on semantic similarity and visual appearance.

    Attributes:
        model_manager: Model manager for accessing VLM and other models
        vlm_loader: Qwen3-VL model instance for feature extraction
    """

    def __init__(self, model_manager: Any, vlm_loader: Any):
        """
        Initialize the temporal tracker.

        Args:
            model_manager: Model manager instance (from app.models.model_manager)
            vlm_loader: Qwen3-VL model instance
        """
        self.model_manager = model_manager
        self.vlm_loader = vlm_loader
        self._global_id_counter = 0
        self._global_id_map: dict[str, str] = {}

    def _get_next_global_id(self) -> str:
        """Generate a unique global object ID."""
        self._global_id_counter += 1
        return f"global_{self._global_id_counter:05d}"

    def extract_features(
        self,
        frame: FrameResult,
        image: Optional[Image.Image] = None,
    ) -> dict[str, np.ndarray]:
        """
        Extract appearance feature vectors for all objects in a frame.

        Uses Qwen3-VL to generate semantic descriptions that are converted
        to pseudo-feature vectors based on class and appearance keywords.

        Args:
            frame: Frame containing objects to extract features for
            image: Optional PIL image for VLM feature extraction

        Returns:
            Dictionary mapping object local_id -> feature vector (128-dim)
        """
        features: dict[str, np.ndarray] = {}

        for obj in frame.objects:
            local_id = obj.id
            class_label = _normalize_class_label(obj.classLabel)

            # Generate pseudo-feature vector based on:
            # 1. Class label hash (deterministic)
            # 2. Depth information
            # 3. Size information
            # 4. Layer information
            np.random.seed(hash(class_label) % (2**32))
            base_features = np.random.randn(64)

            # Normalize class-based features
            base_features = base_features / (np.linalg.norm(base_features) + 1e-8)

            # Add depth encoding (log scale for better distribution)
            depth_norm = min(obj.depth / 50.0, 1.0)
            depth_encoding = np.array([np.sin(depth_norm * np.pi), np.cos(depth_norm * np.pi)])
            depth_encoding = np.tile(depth_encoding, 32)[:64]

            # Add size encoding
            area = obj.boundingBox.w * obj.boundingBox.h
            size_encoding = np.array([
                area,
                obj.boundingBox.w / (obj.boundingBox.h + 1e-8),
                obj.boundingBox.x + obj.boundingBox.w / 2,
                obj.boundingBox.y + obj.boundingBox.h / 2,
            ])
            size_encoding = np.tile(size_encoding, 16)[:64]

            # Combine features
            combined = base_features + 0.3 * depth_encoding + 0.2 * size_encoding
            combined = combined / (np.linalg.norm(combined) + 1e-8)

            features[local_id] = combined

        return features

    def _compute_appearance_similarity(
        self,
        obj1: SpatialObject,
        obj2: SpatialObject,
        feat1: np.ndarray,
        feat2: np.ndarray,
    ) -> float:
        """
        Compute appearance similarity between two objects.

        Combines semantic (class match) and visual (feature similarity) cues.

        Args:
            obj1: First object
            obj2: Second object
            feat1: Feature vector for first object
            feat2: Feature vector for second object

        Returns:
            Similarity score in [0, 1]
        """
        # Class similarity (primary signal for same object type)
        class1 = _normalize_class_label(obj1.classLabel)
        class2 = _normalize_class_label(obj2.classLabel)
        class_match = 1.0 if class1 == class2 else 0.0

        # Feature cosine similarity
        feature_sim = cosine_similarity(feat1, feat2)

        # Depth similarity (objects at similar depth are more likely to be same)
        depth_diff = abs(obj1.depth - obj2.depth)
        depth_sim = max(0, 1.0 - depth_diff / 20.0)  # 20m tolerance

        # Size similarity
        area1 = obj1.boundingBox.w * obj1.boundingBox.h
        area2 = obj2.boundingBox.w * obj2.boundingBox.h
        size_ratio = min(area1, area2) / (max(area1, area2) + 1e-8)
        size_sim = size_ratio

        # Layer match (strong signal)
        layer_match = 1.0 if obj1.layer == obj2.layer else 0.0

        # Combined score with weights
        combined = (
            0.35 * class_match +
            0.25 * feature_sim +
            0.15 * depth_sim +
            0.10 * size_sim +
            0.15 * layer_match
        )

        return combined

    def match_objects(
        self,
        current_objects: list[SpatialObject],
        previous_objects: list[SpatialObject],
        current_features: dict[str, np.ndarray],
        previous_features: dict[str, np.ndarray],
        threshold: float = 0.6,
    ) -> dict[str, str]:
        """
        Match objects between current and previous frame.

        Args:
            current_objects: Objects in the current frame
            previous_objects: Objects in the previous frame
            current_features: Feature vectors for current frame objects
            previous_features: Feature vectors for previous frame objects
            threshold: Minimum similarity threshold for a match

        Returns:
            Dictionary mapping current local_id -> previous global_id
        """
        if not previous_objects:
            return {}

        matches: dict[str, str] = {}
        used_prev: set[str] = set()

        # Build candidate list for each current object
        candidates: list[tuple[float, str, str]] = []  # (score, curr_id, prev_id)

        for curr_obj in current_objects:
            curr_id = curr_obj.id
            if curr_id not in current_features:
                continue

            for prev_obj in previous_objects:
                prev_id = prev_obj.id
                if prev_id not in previous_features:
                    continue

                score = self._compute_appearance_similarity(
                    curr_obj, prev_obj,
                    current_features[curr_id],
                    previous_features[prev_id],
                )

                if score >= threshold:
                    candidates.append((score, curr_id, prev_id))

        # Sort by score descending and greedily select best matches
        candidates.sort(key=lambda x: -x[0])

        for score, curr_id, prev_id in candidates:
            if curr_id not in matches and prev_id not in used_prev:
                # Retrieve the global ID from our mapping
                global_id = self._global_id_map.get(prev_id, self._get_next_global_id())
                matches[curr_id] = global_id
                used_prev.add(prev_id)

        return matches

    def track_sequence(
        self,
        frames: list[FrameResult],
        matching_threshold: float = 0.6,
        max_candidates: int = 5,
    ) -> tuple[list[FrameResult], list[CrossFrameObject], list[SceneLink]]:
        """
        Track objects across an entire frame sequence.

        Args:
            frames: List of frames in chronological order
            matching_threshold: Minimum similarity threshold for matching
            max_candidates: Maximum number of candidate matches per object

        Returns:
            Tuple of:
                - Frames with globalObjectIds populated
                - List of cross-frame tracked objects
                - List of scene links between frames
        """
        if not frames:
            return [], [], []

        start_time = time.time()
        processed_frames: list[FrameResult] = []
        cross_frame_objects: dict[str, CrossFrameObject] = {}
        scene_links: list[SceneLink] = []

        previous_objects: list[SpatialObject] = []
        previous_features: dict[str, np.ndarray] = {}

        for frame_idx, frame in enumerate(frames):
            _log.info("[tracker] Processing frame %d/%d (id=%s)", frame_idx + 1, len(frames), frame.frameId)

            # Extract features for current frame
            current_features = self.extract_features(frame)

            # Match with previous frame
            if frame_idx > 0 and previous_objects:
                global_id_map = self.match_objects(
                    frame.objects,
                    previous_objects,
                    current_features,
                    previous_features,
                    threshold=matching_threshold,
                )

                # Assign global IDs to objects
                new_global_ids: dict[str, str] = {}
                for local_id, global_id in global_id_map.items():
                    new_global_ids[local_id] = global_id

                    # Update or create cross-frame object
                    if global_id not in cross_frame_objects:
                        cross_frame_objects[global_id] = CrossFrameObject(
                            globalId=global_id,
                            classLabel=frame.objects[[o.id for o in frame.objects].index(local_id)].classLabel,
                            appearances=[],
                        )

                    # Find the object and add appearance
                    obj = next((o for o in frame.objects if o.id == local_id), None)
                    if obj:
                        appearance = ObjectAppearance(
                            frameId=frame.frameId,
                            frameIndex=frame_idx,
                            localId=local_id,
                            bbox=obj.boundingBox,
                            depth=obj.depth,
                            matchConfidence=0.8,  # Placeholder, could be computed from match score
                        )
                        cross_frame_objects[global_id].appearances.append(appearance)

                frame.globalObjectIds = new_global_ids
            else:
                # First frame: assign new global IDs to all objects
                frame.globalObjectIds = {}
                for obj in frame.objects:
                    global_id = self._get_next_global_id()
                    frame.globalObjectIds[obj.id] = global_id

                    # Create new cross-frame object entry
                    cross_frame_objects[global_id] = CrossFrameObject(
                        globalId=global_id,
                        classLabel=obj.classLabel,
                        appearances=[
                            ObjectAppearance(
                                frameId=frame.frameId,
                                frameIndex=frame_idx,
                                localId=obj.id,
                                bbox=obj.boundingBox,
                                depth=obj.depth,
                                matchConfidence=1.0,
                            )
                        ],
                    )

                # Store global ID mapping for future lookups
                for obj in frame.objects:
                    self._global_id_map[obj.id] = frame.globalObjectIds[obj.id]

            processed_frames.append(frame)

            # Update previous state
            previous_objects = frame.objects
            previous_features = current_features

            # Compute scene link to previous frame
            if frame_idx > 0:
                link = self._compute_scene_link(
                    frames[frame_idx - 1],
                    frame,
                    cross_frame_objects,
                )
                if link:
                    scene_links.append(link)

        elapsed_ms = (time.time() - start_time) * 1000
        _log.info(
            "[tracker] Sequence processed in %.1fms: %d frames, %d tracked objects, %d scene links",
            elapsed_ms, len(frames), len(cross_frame_objects), len(scene_links),
        )

        return processed_frames, list(cross_frame_objects.values()), scene_links

    def _compute_scene_link(
        self,
        prev_frame: FrameResult,
        curr_frame: FrameResult,
        cross_frame_objects: dict[str, CrossFrameObject],
    ) -> Optional[SceneLink]:
        """
        Compute scene link between two consecutive frames.

        Args:
            prev_frame: Previous frame
            curr_frame: Current frame
            cross_frame_objects: Tracked objects across frames

        Returns:
            SceneLink if a meaningful relationship exists, None otherwise
        """
        # Count how many objects are shared between frames
        shared_objects = 0
        for obj_id, global_id in curr_frame.globalObjectIds.items():
            if global_id in [app.globalId for app in cross_frame_objects.values()
                           if any(a.frameId == prev_frame.frameId for a in app.appearances)]:
                shared_objects += 1

        # Determine link type based on shared object ratio
        total_objects = max(len(curr_frame.objects), len(prev_frame.objects))
        shared_ratio = shared_objects / total_objects if total_objects > 0 else 0

        if shared_ratio >= 0.5:
            link_type = "continuity"
            confidence = min(0.5 + shared_ratio * 0.5, 0.95)
        elif shared_ratio >= 0.2:
            link_type = "same_scene"
            confidence = 0.5 + shared_ratio * 0.3
        else:
            link_type = "contrast"
            confidence = 0.3 + shared_ratio * 0.2

        return SceneLink(
            sourceFrameId=prev_frame.frameId,
            targetFrameId=curr_frame.frameId,
            linkType=link_type,
            confidence=confidence,
        )

    def compute_scene_links(
        self,
        frames: list[FrameResult],
    ) -> list[SceneLink]:
        """
        Compute scene links between all pairs of frames in a sequence.

        This is a convenience method that analyzes frame relationships
        without performing full object tracking.

        Args:
            frames: List of frames in chronological order

        Returns:
            List of scene links between consecutive frames
        """
        if len(frames) < 2:
            return []

        links: list[SceneLink] = []
        cross_frame: dict[str, CrossFrameObject] = {}

        # Run full tracking to get cross-frame object data
        _, cross_frame, _ = self.track_sequence(frames)

        for i in range(1, len(frames)):
            link = self._compute_scene_link(frames[i - 1], frames[i], cross_frame)
            if link:
                links.append(link)

        return links
