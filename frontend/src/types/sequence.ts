// ─────────────────────────────────────────────────────────────────────────────
// AICSS Frontend — Sequence Analysis Types
// v2 API types for frame sequence processing and cross-frame object tracking
// ─────────────────────────────────────────────────────────────────────────────

import type { DetectedObject, SpatialLayer } from '../types';

// Depth layer keys for spatial depth classification
export type DepthLayerKey = 'foreground' | 'midground' | 'background' | 'sky';

// Frame shot type classification
export type FrameType =
  | 'wide_shot'
  | 'medium_shot'
  | 'close_up'
  | 'extreme_close_up'
  | 'over_shoulder'
  | 'pov'
  | 'establishing';

// Tracking mode for cross-frame object matching
export type TrackingMode = 'vlm' | 'semantic' | 'iou' | 'hybrid';

// Scene relationship types between frames
export type SceneLinkType = 'same_scene' | 'same_character' | 'continuity' | 'contrast';

// Object motion pattern classification
export type MotionPattern = 'static' | 'slow' | 'medium' | 'fast' | 'erratic';

// Bounding box with normalized coordinates (0-1)
export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Script-provided scene metadata for sequence analysis
export interface ScriptScene {
  sceneId: string;
  frameId: string;
  imageUrl: string;
  sceneType?: FrameType;
  description?: string;
  characters?: string[];
  location?: string;
  timeOfDay?: string;
}

// Request to analyze an image sequence
export interface AnalyzeSequenceRequest {
  shotId: string;
  frameIds: string[];
  imageUrls: string[];
  projectId?: string;
  enableTracking?: boolean;
  trackingMode?: TrackingMode;
  frameTypes?: FrameType[];
  frameDescriptions?: string[];
  matchingThreshold?: number;
  maxCandidatesPerObject?: number;
}

// Request to analyze sequence from script scenes
export interface AnalyzeFromScriptRequest {
  shotId: string;
  scenes: ScriptScene[];
  projectId?: string;
  enableTracking?: boolean;
  trackingMode?: TrackingMode;
}

// Result for a single frame in the sequence
export interface FrameResult {
  frameId: string;
  frameIndex: number;
  frameType?: FrameType;
  depthMapUrl: string;
  objects: DetectedObject[];
  layers: SpatialLayer[];
  globalObjectIds: Record<string, string>;  // local_id -> global_id
  vlmScene?: string;
  vlmClasses?: string[];
}

// Object appearance in a specific frame
export interface ObjectAppearance {
  frameId: string;
  frameIndex: number;
  localId: string;
  bbox: BoundingBox;
  depth: number;
  matchConfidence: number;
}

// Cross-frame object tracked across multiple frames
export interface CrossFrameObject {
  globalId: string;
  classLabel: string;
  appearances: ObjectAppearance[];
}

// Scene relationship link between frames
export interface SceneLink {
  sourceFrameId: string;
  targetFrameId: string;
  linkType: SceneLinkType;
  confidence: number;
}

// Frame relationship with shared object information
export interface FrameLink {
  sourceFrameId: string;
  targetFrameId: string;
  linkType: SceneLinkType;
  confidence: number;
  sharedObjects?: string[];
  sharedClasses?: string[];
}

// Position in object trajectory
export interface TrajectoryPosition {
  frameId: string;
  x: number;
  y: number;
  depth: number;
}

// Detailed object appearance with layer assignment
export interface ObjectAppearanceDetail {
  frameId: string;
  frameIndex: number;
  localId: string;
  bbox: BoundingBox;
  depth: number;
  matchConfidence: number;
  layer: DepthLayerKey;
}

// Detailed cross-frame object with trajectory analysis
export interface CrossFrameObjectDetail {
  globalId: string;
  classLabel: string;
  totalAppearances: number;
  appearances: ObjectAppearanceDetail[];
  trajectory: {
    positions: TrajectoryPosition[];
    depthRange: [number, number];
    motionPattern: MotionPattern;
  };
  layerHistory: { frameId: string; layer: DepthLayerKey }[];
}

// Processing metadata for sequence analysis
export interface SequenceMetadata {
  totalProcessingTimeMs: number;
  framesProcessed: number;
  framesFailed: number;
  objectsTracked: number;
  trackingMode: TrackingMode;
}

// Complete sequence analysis result
export interface SequenceResult {
  sequenceId: string;
  shotId: string;
  projectId?: string;
  createdAt: string;
  frameCount: number;
  frames: FrameResult[];
  sceneLinks: SceneLink[];
  crossFrameObjects: CrossFrameObject[];
  metadata: SequenceMetadata;
}

// Response for scene links query
export interface SceneLinksResponse {
  sequenceId: string;
  shotId: string;
  frameLinks: FrameLink[];
  crossFrameObjects: CrossFrameObject[];
  statistics: {
    totalLinks: number;
    linksByType: Record<SceneLinkType, number>;
    uniqueObjects: number;
    averageAppearancesPerObject: number;
  };
}
