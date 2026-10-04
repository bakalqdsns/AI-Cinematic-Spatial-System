// ─────────────────────────────────────────────────────────────────────────────
// AICSS Mesh Export Service — calls backend mesh export endpoints.
//
// Thin wrapper around the generated OpenAPI client
// (`generated/v23DMeshExport`). The mesh export endpoints speak snake_case
// for both request and response bodies, matching the existing interfaces
// below — so the wrappers just forward arguments and return the typed
// response. `downloadMeshFile` / `downloadMeshBlob` stay handwritten because
// they build browser download URLs / fetch blobs, which the generated client
// (which returns parsed JSON) doesn't help with.
// ─────────────────────────────────────────────────────────────────────────────
import axios from 'axios';
import type { PolygonPoint } from '../types';
import { generatedClient, DEFAULT_BACKEND } from './generatedClient';

export interface MeshExportResponse {
  mesh_id: string;
  scope: 'object' | 'layer' | 'scene';
  format: string;
  file_name: string | null;
  file_size: number | null;
  file_sha256: string | null;
  object_count: number;
  vertex_count: number;
  face_count: number;
  include_textures: boolean;
  success: boolean;
  error: string | null;
  blender_available: boolean;
  project_id: string | null;
  download_url: string | null;
}

export interface MeshListItem {
  mesh_id: string;
  scope: string;
  target_id: string;
  format: string;
  file_name: string;
  file_size: number;
  file_sha256: string;
  object_count: number;
  vertex_count: number;
  face_count: number;
  include_textures: boolean;
  created_at: string;
  download_url: string;
}

export interface MeshListResponse {
  meshes: MeshListItem[];
}

export interface BlenderCheckResponse {
  available: boolean;
  path: string | null;
  version: string | null;
  message: string;
  error: string | null;
}

export interface ExportObjectsRequest {
  project_id?: string;
  analysis_result: Record<string, unknown>;
  object_ids?: string[];
  object_assets: Record<string, unknown>;
  billboard_offsets: Record<string, unknown>;
  format: 'glb' | 'fbx';
  include_textures: boolean;
}

export interface ExportLayersRequest {
  project_id?: string;
  layer_assets: Record<string, unknown>;
  format: 'glb' | 'fbx';
  include_textures: boolean;
}

export interface StripStep {
  regionId: string;
  baseImageDataUrl: string;
  inpaintResultUrl: string;
  billboardUrl?: string;
  layerPolygon: PolygonPoint[];
  depthLayer: 'foreground' | 'midground' | 'background' | 'sky';
  depthValue: number;
  colorIndex: number;
}

export interface ExportSceneRequest {
  project_id?: string;
  analysis_result: Record<string, unknown>;
  depth_split_result: Record<string, unknown>;
  layer_assets: Record<string, unknown>;
  object_assets: Record<string, unknown>;
  billboard_offsets: Record<string, unknown>;
  regions?: Record<string, unknown>[];
  strip_stack?: StripStep[];
  format: 'glb' | 'fbx';
  include_textures: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Blender availability check
// ─────────────────────────────────────────────────────────────────────────────

export async function checkBlenderAvailable(): Promise<BlenderCheckResponse> {
  return generatedClient.v23DMeshExport.apiCheckBlenderApiAicssV2MeshesCheckGet() as Promise<BlenderCheckResponse>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Export functions
// ─────────────────────────────────────────────────────────────────────────────

export async function exportMeshObjects(
  request: ExportObjectsRequest
): Promise<MeshExportResponse> {
  return generatedClient.v23DMeshExport.apiExportObjectsApiAicssV2MeshesExportObjectsPost({
    requestBody: request as any,
  }) as Promise<MeshExportResponse>;
}

export async function exportMeshLayers(
  request: ExportLayersRequest
): Promise<MeshExportResponse> {
  return generatedClient.v23DMeshExport.apiExportLayersApiAicssV2MeshesExportLayersPost({
    requestBody: request as any,
  }) as Promise<MeshExportResponse>;
}

export async function exportMeshScene(
  request: ExportSceneRequest
): Promise<MeshExportResponse> {
  return generatedClient.v23DMeshExport.apiExportSceneApiAicssV2MeshesExportScenePost({
    requestBody: request as any,
  }) as Promise<MeshExportResponse>;
}

// ─────────────────────────────────────────────────────────────────────────────
// List and manage exports
// ─────────────────────────────────────────────────────────────────────────────

export async function listMeshExports(
  projectId: string
): Promise<MeshListResponse> {
  return generatedClient.v23DMeshExport.apiListMeshesApiAicssV2MeshesListGet({
    projectId,
  }) as unknown as Promise<MeshListResponse>;
}

export async function getMeshInfo(
  meshId: string,
  projectId: string
): Promise<MeshListItem> {
  return generatedClient.v23DMeshExport.apiMeshInfoApiAicssV2MeshesMeshIdInfoGet({
    meshId,
    projectId,
  }) as Promise<MeshListItem>;
}

export async function deleteMeshExport(
  meshId: string,
  projectId: string
): Promise<void> {
  await generatedClient.v23DMeshExport.apiDeleteMeshApiAicssV2MeshesMeshIdDelete({
    meshId,
    projectId,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Download helpers (handwritten — browser blob / anchor downloads)
// ─────────────────────────────────────────────────────────────────────────────

export function downloadMeshFile(
  meshId: string,
  projectId: string,
  filename?: string
): void {
  const url = `${DEFAULT_BACKEND}/api/aicss/v2/meshes/${meshId}/download?project_id=${encodeURIComponent(projectId)}`;
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || `mesh-${meshId}`;
  link.target = '_blank';
  link.click();
}

export async function downloadMeshBlob(
  meshId: string,
  projectId: string
): Promise<Blob> {
  const url = `${DEFAULT_BACKEND}/api/aicss/v2/meshes/${meshId}/download?project_id=${encodeURIComponent(projectId)}`;
  const resp = await axios.get(url, { responseType: 'blob' });
  return resp.data;
}
