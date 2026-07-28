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

// Full analysis result
export interface AicssResult {
  analysisId: string;
  depthMapUrl: string;
  objects: DetectedObject[];
  layers: SpatialLayer[];
  sceneGraph: SceneGraph;
  // VLM detection (always present — computed by Qwen-VL)
  vlmDetectedClasses?: string[];
  vlmDetectedScene?: string;
}

// Layer assignment: objectId -> colorIndex (0-14)
export type LayerAssignments = Record<string, number>;

// Edit mode
export type EditMode = 'director' | 'camera';
export type ImageViewMode = 'depth' | 'original' | 'depth-layer';
// DepthLayerKey: 深度分层系统的键，对应四个深度层级:
//   - foreground: 最近景（人物等前景物体）
//   - midground: 中景
//   - background: 远景/背景
//   - sky: 天际/最远层
// 与 LayerAssignments 不同：DepthLayerKey 是深度分层裁剪的结果（用于纸模立体画），
// 而 LayerAssignments 是 2D 画布上 15 色层的分配系统（objectId -> colorIndex 0-14）
export type DepthLayerKey = 'foreground' | 'midground' | 'background' | 'sky';

// Z 轴常量：每个深度层在 3D 空间中的位置。
// 这些值与 Viewer3D.tsx 中的 DEPTH_LAYER_Z 保持同步，修改此处即修改全局。
export const DEPTH_LAYER_Z: Record<DepthLayerKey, number> = {
  sky: -20,
  background: -12,
  midground: -6,
  foreground: -2,
};

// 深度阈值：用于从灰度深度图（0-255）判断某像素属于哪个层。
// 这些阈值与 depthSplit.ts 中的 DEFAULT_DEPTH_SPLIT_THRESHOLDS 保持同步。
export const DEPTH_LAYER_THRESHOLDS: Record<DepthLayerKey, number> = {
  foreground: 192,  // 192-255 → foreground
  midground: 128,  // 128-191 → midground
  background: 64,    // 64-127  → background
  // <64         → sky
};

// LayerRegion: 任意形状的多边形区域，支持 AI 检测物体和用户手绘两种来源。
// 是多面片3D模型重建系统的核心数据模型——每个 LayerRegion 对应一个独立的 PlaneGeometry billboard。
export interface LayerRegion {
  id: string;                      // uuid，用于唯一标识
  polygon: PolygonPoint[];        // 归一化 0-1 多边形顶点
  depthLayer: DepthLayerKey;       // 该区域所属的深度层
  colorIndex: number;             // 可视化颜色（0-14）
  source: 'ai' | 'manual';        // 来源：AI检测 or 用户手绘
  objectId?: string;              // 若来自 AI 检测物体，关联其 ID
  depthValue?: number;            // 该区域从深度图采样的中值深度（0-255 灰度亮度）
  inpaintMask?: string;           // 该区域的 inpaint mask dataURL（遮罩局部重绘用）
}
// DepthSplitResult: 按深度层级分割后的 RGBA PNG 数据，key 为深度层名称，value 为 base64 data URL
export type DepthSplitResult = Record<DepthLayerKey, string>;

export interface DepthSplitThresholds {
  foregroundMin: number;
  midgroundMin: number;
  backgroundMin: number;
}

// Billboard with RGBA texture for 3D
export interface BillboardAsset {
  objectId: string;
  rgbaUrl: string;  // base64 RGBA PNG from backend
}

export interface DepthLayerBillboardAsset {
  layer: DepthLayerKey;
  rgbaUrl: string;
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

// LAYER_COLORS: 15 种用于 2D 画布可视化的颜色，与 MAX_LAYERS = 15 对应。
// 每个 colorIndex（0-14）映射到一种颜色，用于director模式下给不同深度的物体分配颜色。
// 注意：这与 DepthLayerKey（四层深度分层）是两套独立系统，不可混淆。
export const LAYER_COLORS: string[] = [
  '#E74C3C', '#E67E22', '#F1C40F', '#2ECC71', '#1ABC9C',
  '#3498DB', '#9B59B6', '#E91E63', '#00BCD4', '#FF5722',
  '#607D8B', '#795548', '#9C27B0', '#3F51B5', '#009688',
];

export const MAX_LAYERS = 15;

// ─── Paper Diorama 2.0 ─────────────────────────────────────────────────────────

// PaperDioramaTextures: 后端 API 返回的纸模贴图结构，字段名与后端接口一致（snake_case）。
// 仅包含 URL 字段，不含 layer/objectId 等业务键，用于后端响应反序列化。
export interface PaperDioramaTextures {
  paper_style_url: string;
  thickness_url: string;
  normal_map_url: string;
  outlined_url: string;
  thickness_gray_url: string;
}

export interface PaperDioramaParams {
  thicknessMin: number;
  thicknessMax: number;
  outlineWidth: number;
  colorLevels: number;
  styleStrength: number;
}

export const DEFAULT_PAPER_DIORAMA_PARAMS: PaperDioramaParams = {
  thicknessMin: 1.0,
  thicknessMax: 5.0,
  outlineWidth: 3,
  colorLevels: 12,
  styleStrength: 0.7,
};

// DepthLayerDioramaAsset: 前端 store 中纸模资源的标准形状，包含业务键（layer/objectId）。
// 与 PaperDioramaTextures 的区别：PaperDioramaTextures 是后端 API 响应（snake_case），
// DepthLayerDioramaAsset 是前端规范化后的数据类型（camelCase，含 layer/objectId 键），
// 用于按深度层或按物体管理贴图资源。
export interface DepthLayerDioramaAsset {
  layer: DepthLayerKey;
  rgbaUrl: string;
  thicknessGrayUrl?: string;
  normalMapUrl?: string;
  outlinedUrl?: string;
  paperStyleUrl?: string;
}

export interface ObjectDioramaAsset {
  objectId: string;
  rgbaUrl: string;
  thicknessGrayUrl?: string;
  normalMapUrl?: string;
  outlinedUrl?: string;
  paperStyleUrl?: string;
}

// ─── Sequence Analysis (v2) ────────────────────────────────────────────────────
export * from './sequence';
