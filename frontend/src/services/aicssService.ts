// ─────────────────────────────────────────────────────────────────────────────
// AICSS API Service — calls backend endpoints
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';
import type { AicssResult, BoundingBox, PolygonPoint } from '../types';

const DEFAULT_BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

const client = axios.create({
  baseURL: DEFAULT_BACKEND,
  timeout: 120_000,
});

export async function analyzeImage(imageUrl: string, shotId: string = 'shot_001', apiKey?: string): Promise<AicssResult> {
  const resp = await client.post<AicssResult>('/api/aicss/analyze', {
    imageUrl,
    shotId,
    apiKey: apiKey || undefined,
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
