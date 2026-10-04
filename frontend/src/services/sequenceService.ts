// ─────────────────────────────────────────────────────────────────────────────
// AICSS Sequence Service — v2 API for frame sequence processing.
//
// Thin wrapper around the generated OpenAPI client (`generated/v2Sequence`).
// The v2 sequence endpoints already speak camelCase, so the wrappers below
// just forward arguments and cast the response to the existing frontend types
// — no field mapping required. `createSequenceWebSocket` stays handwritten
// because the OpenAPI spec only describes HTTP endpoints, not the WS upgrade.
// ─────────────────────────────────────────────────────────────────────────────
import type {
  AnalyzeSequenceRequest,
  AnalyzeFromScriptRequest,
  SequenceResult,
  SceneLinksResponse,
  CrossFrameObjectDetail,
  SequenceMetadata,
} from '../types/sequence';
import { generatedClient, DEFAULT_BACKEND } from './generatedClient';

// ─── Sequence Analysis ─────────────────────────────────────────────────────────

export async function analyzeSequence(
  request: AnalyzeSequenceRequest
): Promise<SequenceResult> {
  return generatedClient.v2Sequence.analyzeSequenceApiAicssV2SequencesPost({
    requestBody: request as any,
  }) as unknown as Promise<SequenceResult>;
}

export async function analyzeFromScript(
  request: AnalyzeFromScriptRequest
): Promise<SequenceResult> {
  return generatedClient.v2Sequence.analyzeFromScriptApiAicssV2SequencesFromScriptPost({
    requestBody: request as any,
  }) as unknown as Promise<SequenceResult>;
}

// ─── Query Endpoints ──────────────────────────────────────────────────────────

export async function getSequence(sequenceId: string): Promise<SequenceResult> {
  return generatedClient.v2Sequence.getSequenceApiAicssV2SequencesSequenceIdGet({
    sequenceId,
  }) as unknown as Promise<SequenceResult>;
}

export async function getSceneLinks(
  sequenceId: string
): Promise<SceneLinksResponse> {
  return generatedClient.v2Sequence.getSceneLinksApiAicssV2SequencesSequenceIdSceneLinksGet({
    sequenceId,
  }) as unknown as Promise<SceneLinksResponse>;
}

export async function getCrossFrameObject(
  sequenceId: string,
  globalId: string
): Promise<CrossFrameObjectDetail> {
  return generatedClient.v2Sequence.getCrossFrameObjectApiAicssV2SequencesSequenceIdObjectsGlobalIdGet({
    sequenceId,
    globalId,
  }) as unknown as Promise<CrossFrameObjectDetail>;
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
