// ─────────────────────────────────────────────────────────────────────────────
// AICSS Sequence Service — v2 API for frame sequence processing
// Handles sequence analysis, cross-frame tracking, and WebSocket progress
// ─────────────────────────────────────────────────────────────────────────────

import axios from 'axios';
import type {
  AnalyzeSequenceRequest,
  AnalyzeFromScriptRequest,
  SequenceResult,
  SceneLinksResponse,
  CrossFrameObjectDetail,
  SequenceMetadata,
} from '../types/sequence';

const DEFAULT_BACKEND = import.meta.env.VITE_AICSS_BACKEND || 'http://localhost:8000';

const client = axios.create({
  baseURL: DEFAULT_BACKEND,
  timeout: 30 * 60 * 1000,  // 30 minutes — covers Z-Image + LLM pipelines
});

// ─── Sequence Analysis ─────────────────────────────────────────────────────────

export async function analyzeSequence(
  request: AnalyzeSequenceRequest
): Promise<SequenceResult> {
  const resp = await client.post<SequenceResult>(
    '/api/aicss/v2/sequences',
    request
  );
  return resp.data;
}

export async function analyzeFromScript(
  request: AnalyzeFromScriptRequest
): Promise<SequenceResult> {
  const resp = await client.post<SequenceResult>(
    '/api/aicss/v2/sequences/from-script',
    request
  );
  return resp.data;
}

// ─── Query Endpoints ──────────────────────────────────────────────────────────

export async function getSequence(sequenceId: string): Promise<SequenceResult> {
  const resp = await client.get<SequenceResult>(
    `/api/aicss/v2/sequences/${sequenceId}`
  );
  return resp.data;
}

export async function getSceneLinks(
  sequenceId: string
): Promise<SceneLinksResponse> {
  const resp = await client.get<SceneLinksResponse>(
    `/api/aicss/v2/sequences/${sequenceId}/scene-links`
  );
  return resp.data;
}

export async function getCrossFrameObject(
  sequenceId: string,
  globalId: string
): Promise<CrossFrameObjectDetail> {
  const resp = await client.get<CrossFrameObjectDetail>(
    `/api/aicss/v2/sequences/${sequenceId}/objects/${globalId}`
  );
  return resp.data;
}

// ─── WebSocket Progress ────────────────────────────────────────────────────────

export interface SequenceProgressCallback {
  onConnected?: (totalFrames: number) => void;
  onFrameProgress?: (frameIndex: number, status: string, objectCount?: number) => void;
  onTrackingUpdate?: (globalId: string, classLabel: string, frameId: string) => void;
  onSceneLink?: (sourceId: string, targetId: string, linkType: string, confidence: number) => void;
  onCompleted?: (metadata: SequenceMetadata) => void;
  onError?: (code: string, message: string) => void;
}

export function createSequenceWebSocket(
  sequenceId: string,
  callbacks: SequenceProgressCallback
): WebSocket {
  const ws = new WebSocket(
    `ws://${DEFAULT_BACKEND.replace('http://', '')}/api/aicss/v2/ws/sequences/${sequenceId}`
  );

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'connected':
        callbacks.onConnected?.(data.totalFrames);
        break;
      case 'frame_progress':
        callbacks.onFrameProgress?.(data.frameIndex, data.status, data.objectCount);
        break;
      case 'tracking_update':
        callbacks.onTrackingUpdate?.(data.globalObjectId, data.classLabel, data.frameId);
        break;
      case 'scene_link':
        callbacks.onSceneLink?.(data.sourceFrameId, data.targetFrameId, data.linkType, data.confidence);
        break;
      case 'completed':
        callbacks.onCompleted?.(data);
        break;
      case 'error':
        callbacks.onError?.(data.code, data.message);
        break;
    }
  };

  return ws;
}
