// ─────────────────────────────────────────────────────────────────────────────
// AICSS API Service — calls backend endpoints.
//
// Thin wrapper around the generated OpenAPI client (`generated/aicss`,
// `generated/layers`, `generated/default`). Most v1 endpoints already speak
// camelCase, so the wrappers below just forward arguments and cast the
// response to the existing frontend types.
//
// The paper-diorama / paper-layer / paper-style endpoints are an exception:
// the OpenAPI snapshot's response schema uses camelCase (`paperStyleUrl`,
// `normalMapUrl`, `thicknessGrayUrl`, `outlinedUrl`) but the existing
// components (`App.tsx`, `DepthSplitPanel.tsx`, `DioramaSettingsPanel.tsx`)
// read snake_case fields (`paper_style_url`, `normal_map_url`, ...) from the
// result. To keep those components untouched, the wrappers below map the
// generated camelCase response back to the snake_case `PaperDioramaResult`
// contract the components expect.
// ─────────────────────────────────────────────────────────────────────────────
import type {
  AicssResult,
  BoundingBox,
  PolygonPoint,
  PaperDioramaParams,
  LayerRegion,
} from '../types';
import { DEFAULT_PAPER_DIORAMA_PARAMS } from '../types';
import { generatedClient } from './generatedClient';

export async function analyzeImage(imageUrl: string, shotId: string = 'shot_001'): Promise<AicssResult> {
  return generatedClient.aicss.analyzeApiAicssAnalyzePost({
    requestBody: { imageUrl, shotId },
  }) as unknown as Promise<AicssResult>;
}

export async function generateBillboard(
  imageUrl: string,
  objectId: string,
  boundingBox: BoundingBox,
  polygon?: PolygonPoint[],
): Promise<string> {
  const resp = await generatedClient.aicss.generateBillboardApiAicssBillboardPost({
    requestBody: {
      imageUrl,
      objectId,
      boundingBox,
      polygon: polygon ?? [],
    } as any,
  }) as { billboardUrl?: string };
  return resp.billboardUrl ?? '';
}

export async function generateMultiface(
  imageUrl: string,
  objectId: string,
  boundingBox: BoundingBox,
  polygon?: PolygonPoint[],
): Promise<Record<string, string>> {
  const resp = await generatedClient.aicss.generateMultifaceApiAicssMultifacePost({
    requestBody: {
      imageUrl,
      objectId,
      boundingBox,
      polygon: polygon ?? [],
    } as any,
  }) as { faces?: Record<string, string> };
  return resp.faces ?? {};
}

export async function checkHealth(): Promise<{ status: string; device: string; models_loaded: boolean }> {
  return generatedClient.default.healthHealthGet() as Promise<{ status: string; device: string; models_loaded: boolean }>;
}

/**
 * Per-model availability check. Used by the frontend to surface clear
 * "model not downloaded" hints before triggering expensive inference.
 */
export interface ModelAvailability {
  available: boolean;
  path: string;
  model?: string;
  download_script?: string;
}

export interface ModelsHealth {
  all_ready: boolean;
  device: string;
  lazy_load: boolean;
  models: Record<string, ModelAvailability>;
  missing: Array<{ model: string; path: string; download_hint: string }>;
}

export async function checkModelsHealth(): Promise<ModelsHealth> {
  return generatedClient.default.healthModelsHealthModelsGet() as Promise<ModelsHealth>;
}

export async function inpaintImage(
  imageUrl: string,
  maskDataUrl: string,
  prompt: string,
  projectId?: string,
): Promise<string> {
  const resp = await generatedClient.aicss.inpaintImageApiAicssInpaintPost({
    requestBody: {
      imageUrl,
      maskDataUrl,
      prompt,
      projectId: projectId || undefined,
    } as any,
  }) as { inpaintResultUrl?: string; imageUrl?: string };
  return resp.inpaintResultUrl ?? resp.imageUrl ?? '';
}

export interface OcclusionHole {
  objectId: string;
  maskDataUrl: string;
  polygon: [number, number][];
  whiteRatio: number;
  occluderIds: string[];
  mode: string;
}

export interface OcclusionHolesResult {
  holes: OcclusionHole[];
  mergedMaskDataUrl: string | null;
  mode: string;
  count: number;
}

/** 从 Analyze 物体列表自动生成遮挡空洞 mask（不跑 LaMa）。 */
export async function computeOcclusionHoles(params: {
  objects: Array<{
    id: string;
    maskDataUrl: string;
    depth?: number;
    polygon?: [number, number][];
  }>;
  imageWidth: number;
  imageHeight: number;
  targetObjectIds?: string[];
  mode?: 'peel' | 'occluded_interior';
}): Promise<OcclusionHolesResult> {
  return generatedClient.aicss.occlusionHolesApiAicssOcclusionHolesPost({
    requestBody: {
      objects: params.objects,
      imageWidth: params.imageWidth,
      imageHeight: params.imageHeight,
      targetObjectIds: params.targetObjectIds,
      mode: params.mode ?? 'peel',
    } as any,
  }) as unknown as Promise<OcclusionHolesResult>;
}

export async function applyPaperStyle(
  imageUrl: string,
  params?: Partial<PaperDioramaParams>,
): Promise<string> {
  const merged = { ...DEFAULT_PAPER_DIORAMA_PARAMS, ...params };
  const resp = await generatedClient.aicss.paperStyleTransferApiAicssPaperStylePost({
    requestBody: {
      imageUrl,
      colorLevels: merged.colorLevels,
      styleStrength: merged.styleStrength,
      edgeLow: 50,
      edgeHigh: 150,
    } as any,
  }) as { paperStyleUrl?: string; styledImageUrl?: string };
  // OpenAPI snapshot names this field `paperStyleUrl`; older backend builds
  // returned `styledImageUrl`. Accept either to stay forward + backward compatible.
  return resp.paperStyleUrl ?? resp.styledImageUrl ?? '';
}

export interface PaperDioramaResult {
  paper_style_url: string;
  thickness_url: string;
  normal_map_url: string;
  outlined_url: string;
  thickness_gray_url: string;
}

// "Object Diorama"（物体纸艺场景）：针对单个检测到的物体分别生成纸艺效果，
// 而非整张图片一起处理。典型流程：
// 1. 先由检测模型定位物体的 bounding box 或 polygon 掩码；
// 2. 将该物体的像素传入本函数，分别获得厚度图、法线图、描边等；
// 3. 最终各物体的纸艺层可叠加到同一画布上，或分别打印后手工拼装。
// 与 generatePaperLayer 的区别在于：Layer 是深度分层，Object 是实例分割粒度。
export async function generatePaperDiorama(
  imageUrl: string,
  maskDataUrl: string,
  params?: Partial<PaperDioramaParams>,
): Promise<PaperDioramaResult> {
  const merged = { ...DEFAULT_PAPER_DIORAMA_PARAMS, ...params };
  const data = await generatedClient.aicss.paperDioramaGenerateApiAicssPaperDioramaPost({
    requestBody: {
      imageUrl,
      maskDataUrl,
      thicknessMin: merged.thicknessMin,
      thicknessMax: merged.thicknessMax,
      outlineWidth: merged.outlineWidth,
      colorLevels: merged.colorLevels,
      styleStrength: merged.styleStrength,
    } as any,
  }) as any;
  // Map generated camelCase → existing snake_case contract consumed by
  // App.tsx / DepthSplitPanel.tsx / DioramaSettingsPanel.tsx. Read both names
  // defensively so the wrapper keeps working even if the backend still emits
  // legacy snake_case fields.
  return {
    paper_style_url: data.paperStyleUrl ?? data.paper_style_url ?? '',
    thickness_url: data.thicknessGrayUrl ?? data.thickness_url ?? '',
    normal_map_url: data.normalMapUrl ?? data.normal_map_url ?? '',
    outlined_url: data.outlinedUrl ?? data.outlined_url ?? '',
    thickness_gray_url: data.thicknessGrayUrl ?? data.thickness_gray_url ?? '',
  };
}

// "Layer（图层）" vs "Object（物体）" 的语义区别：
// - Layer（层级）：按深度分层，如前景/中景/背景，对应深度图中的亮度区间。
//   每一层包含该深度范围内所有像素，通常一张图只需 3-4 层即可拼出立体纵深感。
// - Object（物体）：从检测模型返回的单个实例掩码（bounding box 或 polygon），
//   用于针对特定角色的特写展开（多视角、全景拼接等）。
// 本函数处理 Layer 级别的纸艺化：输入一张预切割好的深度层图像（及其掩码），
// 输出纸艺厚度图、法线图、描边等，适合批量处理多图层后叠层组合。
export async function generatePaperLayer(
  layerImageUrl: string,
  layerMaskUrl: string | null,
  params?: Partial<PaperDioramaParams>,
): Promise<PaperDioramaResult> {
  const merged = { ...DEFAULT_PAPER_DIORAMA_PARAMS, ...params };
  const data = await generatedClient.aicss.paperLayerGenerateApiAicssPaperLayerPost({
    requestBody: {
      layerImageUrl,
      layerMaskUrl: layerMaskUrl,
      thicknessMin: merged.thicknessMin,
      thicknessMax: merged.thicknessMax,
      outlineWidth: merged.outlineWidth,
      colorLevels: merged.colorLevels,
      styleStrength: merged.styleStrength,
    } as any,
  }) as any;
  return {
    paper_style_url: data.paperStyleUrl ?? data.paper_style_url ?? '',
    thickness_url: data.thicknessGrayUrl ?? data.thickness_url ?? '',
    normal_map_url: data.normalMapUrl ?? data.normal_map_url ?? '',
    outlined_url: data.outlinedUrl ?? data.outlined_url ?? '',
    thickness_gray_url: data.thicknessGrayUrl ?? data.thickness_gray_url ?? '',
  };
}

// ─── Layer Region support ─────────────────────────────────────────────────────────

/**
 * Extract a billboard texture for a manually drawn LayerRegion.
 * Wraps generateBillboard with the region's polygon.
 * The result is stored in billboardAssets[region.id].
 */
export async function extractRegionBillboard(
  imageUrl: string,
  region: LayerRegion,
): Promise<string> {
  // Compute bounding box from polygon
  const xs = region.polygon.map(([x]) => x);
  const ys = region.polygon.map(([, y]) => y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);

  const boundingBox: BoundingBox = {
    x: minX,
    y: minY,
    w: maxX - minX,
    h: maxY - minY,
  };

  return generateBillboard(imageUrl, region.id, boundingBox, region.polygon);
}
