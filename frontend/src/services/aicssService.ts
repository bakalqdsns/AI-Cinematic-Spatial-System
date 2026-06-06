// ─────────────────────────────────────────────────────────────────────────────
// AICSS API Service — calls backend endpoints
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';
import type {
  AicssResult,
  BoundingBox,
  PolygonPoint,
  PaperDioramaParams,
} from '../types';
import { DEFAULT_PAPER_DIORAMA_PARAMS } from '../types';

// 后端地址，默认指向本地开发服务器
const DEFAULT_BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

// Axios 实例配置：
// - baseURL: 所有请求的公共前缀，由各函数中的路径拼接完整URL
// - timeout: 120秒，深度学习推理和图像生成耗时较长，2分钟可覆盖大部分场景
const client = axios.create({
  baseURL: DEFAULT_BACKEND,
  timeout: 120_000,
});

export async function analyzeImage(imageUrl: string, shotId: string = 'shot_001', apiKey: string): Promise<AicssResult> {
  const resp = await client.post<AicssResult>('/api/aicss/analyze', {
    imageUrl,
    shotId,
    apiKey,
  });
  return resp.data;
}

export async function generateBillboard(
  imageUrl: string,
  objectId: string,
  boundingBox: BoundingBox,
  polygon?: PolygonPoint[],
): Promise<string> {
  const resp = await client.post<{ billboardUrl: string }>('/api/aicss/billboard', {
    imageUrl,
    objectId,
    boundingBox,
    polygon: polygon ?? [],
  });
  return resp.data.billboardUrl;
}

export async function generateMultiface(
  imageUrl: string,
  objectId: string,
  boundingBox: BoundingBox,
  polygon?: PolygonPoint[],
): Promise<Record<string, string>> {
  const resp = await client.post<{ faces: Record<string, string> }>('/api/aicss/multiface', {
    imageUrl,
    objectId,
    boundingBox,
    polygon: polygon ?? [],
  });
  return resp.data.faces;
}

export async function checkHealth(): Promise<{ status: string; device: string; models_loaded: boolean }> {
  const resp = await client.get('/health');
  return resp.data;
}

export async function inpaintImage(
  imageUrl: string,
  maskDataUrl: string,
  prompt: string,
  apiKey?: string,
): Promise<string> {
  const resp = await client.post<{ inpaintResultUrl: string }>('/api/aicss/inpaint', {
    imageUrl,
    maskDataUrl,
    prompt,
    apiKey: apiKey || undefined,
  });
  return resp.data.inpaintResultUrl;
}

export async function applyPaperStyle(
  imageUrl: string,
  params?: Partial<PaperDioramaParams>,
): Promise<string> {
  const merged = { ...DEFAULT_PAPER_DIORAMA_PARAMS, ...params };
  const resp = await client.post<{ styledImageUrl: string }>('/api/aicss/paper-style', {
    imageUrl,
    colorLevels: merged.colorLevels,
    styleStrength: merged.styleStrength,
    edgeLow: 50,
    edgeHigh: 150,
  });
  return resp.data.styledImageUrl;
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
  const resp = await client.post<PaperDioramaResult>('/api/aicss/paper-diorama', {
    imageUrl,
    maskDataUrl,
    thicknessMin: merged.thicknessMin,
    thicknessMax: merged.thicknessMax,
    outlineWidth: merged.outlineWidth,
    colorLevels: merged.colorLevels,
    styleStrength: merged.styleStrength,
  });
  return resp.data;
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
  const resp = await client.post<PaperDioramaResult>('/api/aicss/paper-layer', {
    layerImageUrl,
    layerMaskUrl: layerMaskUrl,
    thicknessMin: merged.thicknessMin,
    thicknessMax: merged.thicknessMax,
    outlineWidth: merged.outlineWidth,
    colorLevels: merged.colorLevels,
    styleStrength: merged.styleStrength,
  });
  return resp.data;
}
