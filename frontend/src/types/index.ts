// ─────────────────────────────────────────────────────────────────────────────
// AICSS Frontend — Shared TypeScript Types
// ─────────────────────────────────────────────────────────────────────────────

// Bounding box normalized 0-1
export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Spatial layer from backend
export interface SpatialLayer {
  id: string;
  name: string;
  zMin: number;
  zMax: number;
  objects: DetectedObject[];
}

// Scene graph node
export interface SceneGraphNode {
  id: string;
  classLabel: string;
  depth: number;
  layer: string;
  relations: Array<{ type: string; targetId: string }>;
}

export interface SceneGraph {
  shotId: string;
  nodes: SceneGraphNode[];
}

// Polygon point: [x_norm, y_norm] in 0-1 range
export type PolygonPoint = [number, number];

// Detected object from backend
export interface DetectedObject {
  id: string;
  classLabel: string;
  depth: number;
  boundingBox: BoundingBox;
  maskDataUrl: string;
  polygon: PolygonPoint[];
  layer: string;
}

// A meter-based depth bucket from the backend config
export interface DepthBucket {
  name: string;
  zMin: number;
  zMax: number;
}

// Full analysis result
export interface AicssResult {
  analysisId: string;
  depthMapUrl: string;
  objects: DetectedObject[];
  layers: SpatialLayer[];
  sceneGraph: SceneGraph;
  // Meter-based depth bucket config (always present)
  depthBuckets: DepthBucket[];
  // VLM detection (always present — computed by Qwen-VL)
  vlmDetectedClasses?: string[];
  vlmDetectedScene?: string;
}

// Layer assignment: objectId -> colorIndex (0-14)
export type LayerAssignments = Record<string, number>;

// Edit mode
export type EditMode = 'director' | 'camera';

// Billboard with RGBA texture for 3D
export interface BillboardAsset {
  objectId: string;
  rgbaUrl: string;  // base64 RGBA PNG from backend
}

// History entry for undo/redo
export interface HistoryEntry {
  assignments: LayerAssignments;
  timestamp: number;
}

// Billboard offset in 3D space
export interface BillboardOffset {
  objectId: string;
  offsetX: number;
  offsetZ: number;
}

// Image crop params
export type ImageSizePreset = '1:1' | '16:9' | '9:16';
export type ResolutionTier = '1K' | '2K';

export interface CropParams {
  size: ImageSizePreset;
  resolution: ResolutionTier;
  cropOffsetX: number;
  cropOffsetY: number;
  actualWidth: number;
  actualHeight: number;
}

// Layer color palette (15 distinct colors)
export const LAYER_COLORS: string[] = [
  '#E74C3C', '#E67E22', '#F1C40F', '#2ECC71', '#1ABC9C',
  '#3498DB', '#9B59B6', '#E91E63', '#00BCD4', '#FF5722',
  '#607D8B', '#795548', '#9C27B0', '#3F51B5', '#009688',
];

export const MAX_LAYERS = 15;

// ─────────────────────────────────────────────────────────────────────────────
// Depth Mode — K-layer slicing
// ─────────────────────────────────────────────────────────────────────────────

// A single percentile quantile value from the backend
export interface DepthQuantile {
  q: number;      // 0-100
  value: number;  // depth in meters
}

// Depth-mode API response from /api/aicss/depth
export interface DepthModeResult {
  depthMapUrl: string;
  objects: DetectedObject[];
  depthBounds: DepthQuantile[];  // 11 entries: q0, q10, ..., q100 (legacy)
  depthBuckets: DepthBucket[];    // meter-based thresholds (uniform with /analyze)
}
